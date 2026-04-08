"""Shared types, enums, dataclasses, and constants for Lacrimosa v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

def _get_config_module():
    """Return the lacrimosa_config module, preferring the scripts-qualified version.

    In tests, conftest loads config via ``scripts.lacrimosa_config``.  When scripts/
    is also on sys.path, a bare ``import lacrimosa_config`` creates a *separate*
    module object with its own ``_config`` cache.  We resolve this by checking
    ``sys.modules`` for the qualified name first.
    """
    import sys

    mod = sys.modules.get("scripts.lacrimosa_config")
    if mod is not None:
        return mod
    import lacrimosa_config as _cfg

    return _cfg


class _LazyFrozenset:
    """Frozenset-like proxy that resolves its value from config on first use."""

    def __init__(self, config_key: str) -> None:
        self._config_key = config_key
        self._resolved: frozenset[str] | None = None

    def _resolve(self) -> frozenset[str]:
        if self._resolved is None:
            cfg = _get_config_module()
            self._resolved = frozenset(cfg.get(self._config_key))
        return self._resolved

    def __contains__(self, item: object) -> bool:
        return item in self._resolve()

    def __iter__(self):  # type: ignore[override]
        return iter(self._resolve())

    def __len__(self) -> int:
        return len(self._resolve())

    def __repr__(self) -> str:
        return repr(self._resolve())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, frozenset):
            return self._resolve() == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._resolve())


# -- Enums -------------------------------------------------------------------


class SignalCategory(StrEnum):
    PAIN_POINT = "pain-point"
    FEATURE_GAP = "feature-gap"
    ERROR_PATTERN = "error-pattern"
    CHURN_SIGNAL = "churn-signal"
    COMPETITOR_MOVE = "competitor-move"
    QUALITY_ISSUE = "quality-issue"


class ValidationStatus(StrEnum):
    PENDING = "pending"
    VALIDATED = "validated"
    ARCHIVED = "archived"
    ACTED = "acted"


class SignalSource(StrEnum):
    REDDIT = "reddit"
    GA4 = "ga4"
    CLOUD_LOGGING = "cloud-logging"
    FEEDBACK = "feedback"
    COMPETITOR = "competitor"
    STRIPE = "stripe"
    USAGE = "usage"
    BUG_REPORT = "bug-report"
    SUPPORT_EMAIL = "support-email"


class SensorName(StrEnum):
    SOCIAL_LISTENER = "social-listener"
    FUNNEL_ANALYZER = "funnel-analyzer"
    COMPETITOR_MONITOR = "competitor-monitor"
    ERROR_PATTERN_DETECTOR = "error-pattern-detector"
    FEEDBACK_ANALYZER = "feedback-analyzer"
    PAYMENT_ANOMALY_DETECTOR = "payment-anomaly-detector"
    USAGE_PATTERN_ANALYZER = "usage-pattern-analyzer"
    INTAKE_TRIAGE = "intake-triage"


class ThrottleLevel(StrEnum):
    green = "green"
    yellow = "yellow"
    red = "red"


class IssueRouting(StrEnum):
    ARCHIVED = "archived"
    BACKLOG = "backlog"
    ACTION = "action"


class TrustEvent(StrEnum):
    PR_REVIEW_REJECTED = "pr_review_rejected"
    PR_REVIEW_ITERATION_2PLUS = "pr_review_iteration_2plus"
    PR_REVERTED = "pr_reverted"
    WORKER_ESCALATED = "worker_escalated"
    TRUST_PROMOTED = "trust_promoted"
    TRUST_CONTRACTED = "trust_contracted"
    RETRO_OBSERVATION = "retro_observation"
    # -- Self-observability --
    METRIC_DEGRADATION = "metric_degradation"
    METRIC_OPPORTUNITY = "metric_opportunity"
    AUTO_TUNE_APPLIED = "auto_tune_applied"
    AUTO_TUNE_REVERTED = "auto_tune_reverted"


class CeremonyName(StrEnum):
    STANDUP = "standup"
    SPRINT_PLANNING = "sprint_planning"
    BACKLOG_GROOMING = "backlog_grooming"
    SPRINT_RETRO = "sprint_retro"
    WEEKLY_SUMMARY = "weekly_summary"


class SteeringCommandType(StrEnum):
    REWORK = "rework"
    RECONSIDER = "reconsider"
    PAUSE = "pause"
    RESUME = "resume"
    PRIORITIZE = "prioritize"
    DEPRIORITIZE = "deprioritize"
    CANCEL = "cancel"


# -- Dataclasses -------------------------------------------------------------


@dataclass
class ScoringDimensions:
    mission_alignment: float  # 0.0-2.5
    feasibility: float  # 0.0-2.5
    impact: float  # 0.0-2.5
    urgency: float  # 0.0-2.5

    def composite(self) -> float:
        return self.mission_alignment + self.feasibility + self.impact + self.urgency


@dataclass
class RevertPath:
    file: str
    old_value: str
    new_value: str
    line: int | None = None


@dataclass
class LearningEntry:
    id: str  # "lrn-{uuid}"
    event_type: TrustEvent
    issue_id: str
    agent_type: str
    root_cause: str
    pattern: str
    adjustment: str
    severity: str  # "low" | "medium" | "high"
    timestamp: str  # ISO 8601
    applied: bool
    reverted: bool
    revert_path: RevertPath | None = None


@dataclass
class TrustEventData:
    """A trust-affecting event emitted by the conductor."""

    event_type: str
    issue_id: str
    domain: str
    agent_type: str
    timestamp: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class SteeringCommand:
    """A parsed steering command from a Linear comment."""

    command_type: SteeringCommandType
    issue_id: str
    comment_id: str
    context: str  # Additional text from the comment (instructions, reasons)


@dataclass
class WorkerEntry:
    issue_id: str
    pid: int
    worktree_name: str
    phase: str
    started_at: str  # ISO 8601
    domain: str


# -- Constants ---------------------------------------------------------------

SCORING_MAX_PER_DIMENSION: float = 2.5
SCORING_DIMENSIONS: tuple[str, ...] = (
    "mission_alignment",
    "feasibility",
    "impact",
    "urgency",
)
ACT_THRESHOLD: float = 6.0
BORDERLINE_RANGE: tuple[float, float] = (6.0, 7.0)
EXTERNAL_CRAWL_CAP: int = 50

AUTONOMOUS_DOMAINS = _LazyFrozenset("domains.autonomous")
APPROVAL_REQUIRED_DOMAINS = _LazyFrozenset("domains.approval_required")

REQUIRED_SIGNAL_FIELDS: frozenset[str] = frozenset(
    {
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
)

HARDCODED_MAX_CONCURRENT_WORKERS: int = 5
HARDCODED_MAX_ISSUES_PER_DAY: int = 15
HARDCODED_MAX_DISCOVERY_PER_DAY: int = 5
HARDCODED_MAX_EXTERNAL_CRAWLS: int = 100
HARDCODED_MAX_WORKER_RUNTIME_MINUTES: int = 60

# -- Learning Constants ------------------------------------------------------

VALID_ADJUSTMENT_TYPES: frozenset[str] = frozenset(
    {
        "prompt_refinement",
        "guardrail_addition",
        "classification_fix",
        "scope_calibration",
        "threshold_adjustment",
        "cadence_adjustment",
        "trust_tier_promotion",
    }
)
VALID_SEVERITIES: frozenset[str] = frozenset(
    {
        "low",
        "medium",
        "high",
        "critical",
    }
)
VALID_LEARNING_STATUSES: frozenset[str] = frozenset(
    {
        "pending",
        "in_review",
        "approved",
        "reverted",
    }
)
REQUIRED_LEARNING_FIELDS: frozenset[str] = frozenset(
    {
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
)
REQUIRED_ADJUSTMENT_FIELDS: frozenset[str] = frozenset(
    {
        "type",
        "target_file",
        "target_path",
        "old_value",
        "new_value",
        "description",
    }
)
EVENT_SEVERITY_MAP: dict[str, str] = {
    "pr_reverted": "high",
    "worker_escalated": "high",
    "pr_review_rejected": "medium",
    "pr_review_iteration_2plus": "medium",
    "trust_contracted": "medium",
    "trust_promoted": "low",
    "metric_degradation": "high",
    "metric_opportunity": "low",
    "auto_tune_applied": "medium",
    "auto_tune_reverted": "medium",
}


@dataclass
class CeremonyResult:
    ceremony: str
    success: bool
    timestamp: str
    linear_url: str | None
    summary: str
    data: dict[str, Any]
    error: str | None


@dataclass
class GroomingActions:
    re_scored: int = 0
    decomposed: int = 0
    merged: int = 0
    archived: int = 0


# -- Ceremony Constants ------------------------------------------------------

CEREMONY_RETRY_ATTEMPTS: int = 3
CEREMONY_RETRY_BACKOFF_BASE: float = 10.0
CEREMONY_MAX_EXECUTION_MINUTES: dict[str, int] = {
    "standup": 2,
    "sprint_planning": 5,
    "backlog_grooming": 10,
    "sprint_retro": 5,
    "weekly_summary": 10,
}
GROOMING_STALE_THRESHOLD_HOURS: int = 12
GROOMING_FILE_THRESHOLD: int = 15
GROOMING_SIMILARITY_THRESHOLD: float = 0.8
GROOMING_INACTIVE_THRESHOLD_HOURS: int = 48

# -- Self-Monitor Enums -----------------------------------------------------


class FindingClassification(StrEnum):
    BREAKING_CHANGE = "breaking_change"
    NEW_FEATURE = "new_feature"
    PRICING_CHANGE = "pricing_change"
    NEW_MODEL = "new_model"
    DEPRECATION = "deprecation"
    SECURITY_ADVISORY = "security_advisory"


class FindingDecision(StrEnum):
    AUTO_ADOPT = "auto_adopt"
    HUMAN_REVIEW = "human_review"
    ARCHIVE = "archive"


# -- Self-Monitor Dataclasses ------------------------------------------------


@dataclass
class MetaSensorSnapshot:
    """Point-in-time metrics about Lacrimosa's own performance."""

    timestamp: str  # ISO 8601
    throughput: dict[str, float]
    quality: dict[str, float]
    cost: dict[str, float]
    discovery: dict[str, float]
    ceremony: dict[str, Any]
    system: dict[str, Any]
    specialists: dict[str, dict] = field(default_factory=dict)


@dataclass
class ReactiveRule:
    """Threshold rule that fires when a metric degrades past a limit."""

    name: str
    metric_path: str  # dot-path into MetaSensorSnapshot
    operator: str  # ">" | "<" | ">=" | "<="
    threshold: float
    window_days: int
    action: str
    severity: str  # "low" | "medium" | "high"
    adjustment: dict[str, Any] | None = None


@dataclass
class ProactiveRule:
    """Threshold rule that fires when a metric sustains improvement."""

    name: str
    metric_path: str
    operator: str
    threshold: float
    window_days: int
    action: str
    adjustment: dict[str, Any] | None = None


@dataclass
class AutoTuneEntry:
    """Record of an auto-tuning change with impact tracking."""

    id: str  # "tune-{uuid8}"
    timestamp: str  # ISO 8601
    trigger_rule: str
    change_type: str  # "reactive" | "proactive"
    action: str
    target_file: str
    target_path: str
    old_value: Any
    new_value: Any
    applied_at: str | None
    impact_window_hours: int
    measured_impact: dict[str, Any] | None
    reverted: bool
    learning_id: str | None


@dataclass
class ToolchainFinding:
    """A detected change in the Anthropic/Claude Code toolchain."""

    id: str  # "tcf-{uuid8}"
    source: str
    url: str
    timestamp: str  # ISO 8601
    classification: str  # FindingClassification value
    title: str
    summary: str
    raw_content: str  # max 2000 chars
    relevance: float  # 0.0-10.0
    impact: float  # 0.0-10.0
    risk: float  # 0.0-10.0
    effort_estimate: str  # "low" | "medium" | "high"
    decision: str  # FindingDecision value
    issue_id: str | None
    applied: bool


# -- Self-Monitor Constants --------------------------------------------------

SELF_MONITOR_CADENCE_HOURS: int = 4
TOOLCHAIN_MONITOR_CADENCE_HOURS: int = 6
AUTO_TUNE_LOG_SIZE_WARN_BYTES: int = 524_288  # 512 KB
TOOLCHAIN_LOG_SIZE_WARN_BYTES: int = 524_288
MAX_TUNE_ENTRIES_PER_CYCLE: int = 3
DEFAULT_IMPACT_WINDOW_HOURS: int = 24


# -- Type Aliases ------------------------------------------------------------

SignalDict = dict[str, Any]
StateDict = dict[str, Any]
ConfigDict = dict[str, Any]
