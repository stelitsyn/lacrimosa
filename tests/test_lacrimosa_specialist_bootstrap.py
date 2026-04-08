"""TDD tests for specialist bootstrap helper."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.lacrimosa_specialist_bootstrap import (
    bootstrap_specialist,
    build_loop_prompt,
    build_cadence_str,
)


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    config = {
        "specialists": {
            "discovery": {
                "tmux_session": "lacrimosa-discovery",
                "skill_file": "specialists/discovery.md",
                "loops": [{"cadence": "30m", "trigger": "discovery-cycle"}],
                "writes_to_state": ["discovery.*", "learning_events.*"],
                "health_check": {"max_silence": "35m"},
            },
            "engineering": {
                "tmux_session": "lacrimosa-engineering",
                "skill_file": "specialists/engineering.md",
                "loops": [{"cadence": "5m", "trigger": "engineering-cycle"}],
                "writes_to_state": [
                    "pipeline.*",
                    "issues.*",
                    "trust_scores.*",
                    "learning_events.*",
                ],
                "health_check": {"max_silence": "10m"},
            },
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(config))
    return path


class TestBootstrapSpecialist:
    def test_returns_config_block(self, config_path: Path):
        result = bootstrap_specialist("discovery", config_path)
        assert result["tmux_session"] == "lacrimosa-discovery"
        assert result["skill_file"] == "specialists/discovery.md"

    def test_raises_on_unknown_specialist(self, config_path: Path):
        with pytest.raises(ValueError, match="not found"):
            bootstrap_specialist("nonexistent", config_path)

    def test_returns_writes_to_state(self, config_path: Path):
        result = bootstrap_specialist("discovery", config_path)
        assert "discovery.*" in result["writes_to_state"]

    def test_returns_health_check(self, config_path: Path):
        result = bootstrap_specialist("engineering", config_path)
        assert result["health_check"]["max_silence"] == "10m"


class TestBuildLoopPrompt:
    def test_contains_cadence(self, config_path: Path):
        config = bootstrap_specialist("discovery", config_path)
        prompt = build_loop_prompt("discovery", config)
        assert "30m" in prompt or "discovery" in prompt

    def test_contains_skill_file_reference(self, config_path: Path):
        config = bootstrap_specialist("discovery", config_path)
        prompt = build_loop_prompt("discovery", config)
        assert "skill" in prompt.lower() or "specialist" in prompt.lower()

    def test_contains_heartbeat(self, config_path: Path):
        config = bootstrap_specialist("discovery", config_path)
        prompt = build_loop_prompt("discovery", config)
        assert "heartbeat" in prompt.lower() or "transaction" in prompt.lower()

    def test_contains_trigger_label(self, config_path: Path):
        config = bootstrap_specialist("discovery", config_path)
        prompt = build_loop_prompt("discovery", config)
        assert "discovery-cycle" in prompt


class TestBuildCadenceStr:
    def test_extracts_first_cadence(self, config_path: Path):
        config = bootstrap_specialist("discovery", config_path)
        assert build_cadence_str(config) == "30m"

    def test_default_when_no_loops(self):
        assert build_cadence_str({}) == "10m"
