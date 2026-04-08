"""Shared test configuration for Lacrimosa tests.

Provides a test config.yaml so all lacrimosa_config.get() calls work in tests.
"""
import sys
from pathlib import Path

import pytest

# Ensure repo root + scripts/ are importable
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scripts.lacrimosa_config import get_config, reset  # noqa: E402


TEST_CONFIG_YAML = """\
product:
  name: "TestProduct"
  description: "A test product"
  slug: "testproduct"
conductor:
  project_root: "/tmp/test-project"
  default_project: "Platform"
  poll_interval_seconds: 300
  worktree_base: /tmp/lacrimosa-test
  state_file: /tmp/lacrimosa-test/state.db
  log_file: /tmp/lacrimosa-test/conductor.log
linear:
  workspace_slug: "test-workspace"
  issue_prefix: "TST"
  team_members:
    - key: "owner"
      id: "00000000-0000-0000-0000-000000000001"
      name: "Test Owner"
    - key: "dev"
      id: "00000000-0000-0000-0000-000000000002"
      name: "Test Developer"
    - key: "lacrimosa"
      id: "00000000-0000-0000-0000-000000000099"
      name: "Lacrimosa"
domains:
  autonomous:
    - "Platform"
    - "Marketing"
    - "Internationalization"
  approval_required:
    - "Billing"
    - "Mobile"
    - "Infrastructure"
  out_of_scope:
    - "Legal"
project_routing:
  Platform:
    - "feature"
    - "workflow"
    - "integration"
    - "automation"
    - "platform"
    - "onboarding"
  Billing:
    - "billing"
    - "payments"
    - "stripe"
    - "subscription"
  Mobile:
    - "mobile"
    - "android"
    - "ios"
  Infrastructure:
    - "infra"
    - "devops"
    - "deployment"
    - "ci_cd"
  Marketing:
    - "marketing"
    - "seo"
    - "content"
    - "growth"
data_sources:
  gcp:
    project_id: "test-project-id"
    cloud_sql_instances:
      - region: "us-central1"
        instance: "test-db-us"
      - region: "europe-west1"
        instance: "test-db-eu"
verification:
  frontend_path_patterns:
    - "frontend/"
watchdog:
  bundle_id: "com.test.lacrimosa-watchdog"
sensors:
  prompt_context:
    product_name: "TestProduct"
    product_description: "A test product"
"""


@pytest.fixture(autouse=True)
def _lacrimosa_test_config(tmp_path):
    """Auto-load test config before every test, reset after."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(TEST_CONFIG_YAML)
    reset()
    # Also reset any lazy caches in modules that cache config at call time
    try:
        from scripts import lacrimosa_intake
        lacrimosa_intake._domain_project_map = None
    except (ImportError, AttributeError):
        pass
    get_config(config_file)
    yield
    reset()
