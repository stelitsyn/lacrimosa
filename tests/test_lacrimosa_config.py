"""Tests for lacrimosa_config — the single config loader."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure scripts/ and repo root are importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.lacrimosa_config import get, get_config, reset  # noqa: E402


VALID_CONFIG = """\
product:
  name: "TestProduct"
  description: "A test product"
  slug: "testproduct"
conductor:
  project_root: "/tmp/test-project"
  default_project: "Platform"
linear:
  workspace_slug: "test-workspace"
  issue_prefix: "TST"
  team_members:
    - key: "owner"
      id: "00000000-0000-0000-0000-000000000001"
      name: "Test Owner"
domains:
  autonomous:
    - "Platform"
    - "Billing"
  approval_required:
    - "Security"
  out_of_scope:
    - "Legal"
project_routing:
  Platform:
    - "platform"
    - "api"
  Marketing:
    - "seo"
    - "content"
data_sources:
  gcp:
    project_id: "test-project-id"
    cloud_sql_instances:
      - region: "us-central1"
        instance: "test-db-us"
verification:
  frontend_path_patterns:
    - "frontend/"
watchdog:
  bundle_id: "com.test.lacrimosa-watchdog"
"""


def _write_config(tmp_path: Path, content: str = VALID_CONFIG) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(content)
    return p


@pytest.fixture(autouse=True)
def _reset():
    reset()
    yield
    reset()


class TestGetConfig:
    def test_loads_valid_config(self, tmp_path):
        path = _write_config(tmp_path)
        cfg = get_config(path)
        assert cfg["product"]["name"] == "TestProduct"

    def test_caches_result(self, tmp_path):
        path = _write_config(tmp_path)
        cfg1 = get_config(path)
        cfg2 = get_config()  # no path — uses cache
        assert cfg1 is cfg2

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            get_config(Path("/nonexistent/path/config.yaml"))

    def test_missing_required_key_raises(self, tmp_path):
        path = _write_config(tmp_path, "product:\n  name: 'Partial'\n")
        with pytest.raises(ValueError, match="Required config key missing"):
            get_config(path)

    def test_all_required_keys_validated(self, tmp_path):
        path = _write_config(tmp_path, "product:\n  name: 'X'\n  description: 'Y'\n  slug: 'z'\n")
        with pytest.raises(ValueError, match="conductor.project_root"):
            get_config(path)


class TestGet:
    def test_dot_path_access(self, tmp_path):
        get_config(_write_config(tmp_path))
        assert get("product.name") == "TestProduct"
        assert get("linear.workspace_slug") == "test-workspace"

    def test_nested_list(self, tmp_path):
        get_config(_write_config(tmp_path))
        assert get("domains.autonomous") == ["Platform", "Billing"]

    def test_nested_dict(self, tmp_path):
        get_config(_write_config(tmp_path))
        routing = get("project_routing")
        assert "Platform" in routing

    def test_missing_key_raises(self, tmp_path):
        get_config(_write_config(tmp_path))
        with pytest.raises(KeyError, match="nonexistent"):
            get("nonexistent.key")

    def test_default_value(self, tmp_path):
        get_config(_write_config(tmp_path))
        assert get("nonexistent", "fallback") == "fallback"

    def test_default_none(self, tmp_path):
        get_config(_write_config(tmp_path))
        assert get("nonexistent", None) is None
