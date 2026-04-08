"""Signal schema validation, persistence, rotation, and factory functions."""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from lacrimosa_types import (
    REQUIRED_SIGNAL_FIELDS,
    SignalCategory,
    ValidationStatus,
)

logger = logging.getLogger(__name__)

# -- Constants ---------------------------------------------------------------

SIGNALS_DIR: Path = Path.home() / ".claude" / "lacrimosa" / "signals"

VALID_CATEGORIES = {v.value for v in SignalCategory}
VALID_VALIDATION_STATUSES = {v.value for v in ValidationStatus}


# -- Public Functions --------------------------------------------------------


def create_signal(
    source: str,
    sensor: str,
    category: str,
    raw_content: str,
    summary: str,
    reach: int,
    sentiment: float,
    relevance_tags: list[str],
    evidence_links: list[str],
    **extra_fields: Any,
) -> dict[str, Any]:
    """Create a valid signal dict with auto-generated id and timestamp."""
    if category not in VALID_CATEGORIES:
        msg = f"Invalid category: {category!r}. Must be one of {sorted(VALID_CATEGORIES)}"
        raise ValueError(msg)
    if not (-1.0 <= sentiment <= 1.0):
        msg = f"Invalid sentiment: {sentiment}. Must be in [-1, 1]"
        raise ValueError(msg)

    sig: dict[str, Any] = {
        "id": f"sig-{uuid.uuid4().hex[:12]}",
        "source": source,
        "sensor": sensor,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "raw_content": raw_content,
        "summary": summary,
        "reach": reach,
        "sentiment": sentiment,
        "relevance_tags": relevance_tags,
        "evidence_links": evidence_links,
        "validation_status": "pending",
        "composite_score": None,
    }
    sig.update(extra_fields)
    return sig


def validate_signal(signal: dict[str, Any]) -> list[str]:
    """Validate a signal dict against the schema. Returns list of error strings."""
    errors: list[str] = []

    missing = REQUIRED_SIGNAL_FIELDS - set(signal.keys())
    if missing:
        errors.append(f"Missing required fields: {sorted(missing)}")

    cat = signal.get("category")
    if cat is not None and cat not in VALID_CATEGORIES:
        errors.append(f"Invalid category: {cat!r}. Must be one of {sorted(VALID_CATEGORIES)}")

    sentiment = signal.get("sentiment")
    if sentiment is not None and not (-1.0 <= sentiment <= 1.0):
        errors.append(f"Sentiment {sentiment} out of range [-1, 1]")

    vs = signal.get("validation_status")
    if vs is not None and vs not in VALID_VALIDATION_STATUSES:
        errors.append(
            f"Invalid validation_status: {vs!r}. "
            f"Must be one of {sorted(VALID_VALIDATION_STATUSES)}"
        )

    cs = signal.get("composite_score")
    if cs is not None and not isinstance(cs, (int, float)):
        errors.append(f"composite_score must be None or numeric, got {type(cs).__name__}")

    return errors


def persist_signal(
    signal: dict[str, Any],
    signals_dir: Path | None = None,
) -> Path:
    """Persist a signal as JSON file in date-partitioned directory."""
    errors = validate_signal(signal)
    if errors:
        raise ValueError(f"Invalid signal: {'; '.join(errors)}")

    base = signals_dir or SIGNALS_DIR
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day_dir = base / today
    day_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{signal['id']}.json"
    path = day_dir / filename
    path.write_text(json.dumps(signal, indent=2, default=str))
    path.chmod(0o600)
    logger.debug("Persisted signal %s to %s", signal["id"], path)
    return path


def load_signal(path: Path) -> dict[str, Any]:
    """Load a signal dict from a JSON file."""
    return json.loads(path.read_text())


def list_signals(
    signals_dir: Path | None = None,
    date: str | None = None,
) -> list[Path]:
    """List signal file paths, optionally filtered by date (YYYY-MM-DD)."""
    base = signals_dir or SIGNALS_DIR
    if not base.exists():
        return []

    if date:
        day_dir = base / date
        if not day_dir.exists():
            return []
        return sorted(day_dir.glob("sig-*.json"))

    result: list[Path] = []
    for day_dir in sorted(base.iterdir()):
        if day_dir.is_dir():
            result.extend(sorted(day_dir.glob("sig-*.json")))
    return result


def rotate_signals(
    signals_dir: Path | None = None,
    retention_days: int = 7,
) -> int:
    """Remove signal directories older than retention_days. Returns count deleted."""
    base = signals_dir or SIGNALS_DIR
    if not base.exists():
        return 0

    cutoff = datetime.now(timezone.utc).date() - timedelta(days=retention_days)
    deleted = 0

    for day_dir in list(base.iterdir()):
        if not day_dir.is_dir():
            continue
        try:
            dir_date = datetime.strptime(day_dir.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if dir_date < cutoff:
            shutil.rmtree(day_dir)
            logger.info("Rotated signal directory %s", day_dir.name)
            deleted += 1

    return deleted
