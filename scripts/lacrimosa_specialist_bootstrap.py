"""Generic specialist bootstrap — reads config, builds one-shot runner."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from scripts import lacrimosa_config

DEFAULT_CONFIG_PATH = Path.home() / ".claude" / "lacrimosa" / "config.yaml"


def bootstrap_specialist(
    name: str, config_path: Path | str = DEFAULT_CONFIG_PATH
) -> dict[str, Any]:
    """Read config, validate specialist exists, return its config block."""
    config = yaml.safe_load(Path(config_path).read_text())
    specialists = config.get("specialists", {})
    if name not in specialists:
        raise ValueError(
            f"Specialist '{name}' not found in config. "
            f"Available: {list(specialists.keys())}"
        )
    return specialists[name]


def _cadence_to_seconds(cadence: str) -> int:
    """Convert cadence string like '30m', '5m', '6h', '24h' to seconds."""
    match = re.match(r"(\d+)\s*([mhd])", cadence.strip().lower())
    if not match:
        return 600  # default 10m
    value, unit = int(match.group(1)), match.group(2)
    multipliers = {"m": 60, "h": 3600, "d": 86400}
    return value * multipliers[unit]


def build_cadence_seconds(config: dict[str, Any]) -> int:
    """Extract the shortest cadence in seconds."""
    loops = config.get("loops", [])
    cadence_str = loops[0]["cadence"] if loops else "10m"
    return _cadence_to_seconds(cadence_str)


def build_cadence_str(config: dict[str, Any]) -> str:
    """Extract the shortest cadence string (e.g. '30m')."""
    loops = config.get("loops", [])
    return loops[0]["cadence"] if loops else "10m"


def build_oneshot_prompt(name: str, config: dict[str, Any]) -> str:
    """Build the one-shot prompt for a single specialist cycle.

    Used with `claude -p` for stateless execution — each cycle gets a fresh
    context window. No context accumulation between cycles.
    """
    loops = config.get("loops", [])
    trigger = loops[0].get("trigger", f"{name}-cycle") if loops else f"{name}-cycle"
    skill_file = config.get("skill_file", f"specialists/{name}.md")
    skill_path = f"~/.claude/skills/lacrimosa/{skill_file}"

    return (
        f"Execute one {name} specialist cycle. "
        f"Read the skill file at {skill_path} and follow the cycle steps exactly. "
        f"Label: {trigger}. "
        f"Heartbeat update via sm.transaction(\"{name}\") commit."
    )


def build_tmux_command(name: str, config: dict[str, Any]) -> str:
    """Build the tmux session command for a specialist.

    Returns a shell command that loops: run one-shot `claude -p` per cycle,
    sleep for cadence, repeat. Each `claude -p` invocation gets a fresh
    context window, preventing token accumulation.
    """
    prompt = build_oneshot_prompt(name, config)
    cadence_s = build_cadence_seconds(config)
    project_dir = lacrimosa_config.get("conductor.project_root")

    # Escape single quotes in prompt for shell embedding
    escaped_prompt = prompt.replace("'", "'\\''")

    return (
        f"cd {project_dir} && "
        f"while true; do "
        f"claude -p --dangerously-skip-permissions '{escaped_prompt}'; "
        f"sleep {cadence_s}; "
        f"done"
    )


# Keep old name as alias for backward compat during transition
build_loop_prompt = build_oneshot_prompt
