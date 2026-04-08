"""Lacrimosa configuration loader.

Single module all other scripts import for config access.
No module reads config independently.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_MISSING = object()
_config: dict | None = None

REQUIRED_KEYS = (
    "product.name",
    "product.description",
    "product.slug",
    "conductor.project_root",
    "linear.workspace_slug",
    "linear.issue_prefix",
    "domains.autonomous",
)

DEFAULT_CONFIG_PATH = Path("~/.claude/lacrimosa/config.yaml").expanduser()


def get_config(path: Path | None = None) -> dict:
    """Load and validate config YAML. Caches after first successful load."""
    global _config
    if _config is not None:
        return _config
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path) as f:
        loaded = yaml.safe_load(f)
    if not isinstance(loaded, dict):
        raise ValueError(f"Config must be a YAML mapping, got {type(loaded).__name__}")
    _config = loaded
    _validate(_config)
    return _config


def get(key: str, default: Any = _MISSING) -> Any:
    """Dot-path accessor. Example: get('linear.workspace_slug')."""
    cfg = get_config()
    try:
        return _resolve(cfg, key)
    except KeyError:
        if default is not _MISSING:
            return default
        raise KeyError(f"Config key not found: {key}")


def reset() -> None:
    """Reset cached config. For testing only."""
    global _config
    _config = None


def _validate(cfg: dict) -> None:
    for key in REQUIRED_KEYS:
        try:
            _resolve(cfg, key)
        except KeyError:
            raise ValueError(f"Required config key missing: {key}")


def _resolve(d: dict, key: str) -> Any:
    parts = key.split(".")
    current = d
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            raise KeyError(key)
        current = current[part]
    return current
