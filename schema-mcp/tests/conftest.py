"""Test fixtures for schema MCP server tests."""

import shutil
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def temp_schemas_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary schemas directory for testing."""
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    yield schemas_dir
    shutil.rmtree(schemas_dir, ignore_errors=True)


@pytest.fixture
def sample_schema_content() -> str:
    """Sample schema markdown content for testing."""
    return """# Test Schema

This is a test schema file for unit testing.

## Overview

Test schema content with some searchable keywords like authentication and database.

## Details

More content here for testing search functionality.
"""


@pytest.fixture
def sample_index_content() -> str:
    """Sample SCHEMA_INDEX.md content for testing."""
    return """# Schema Index

This index groups all schema documents under `schemas/` by domain.

**Last Updated**: 2025-01-01
**Total Schemas**: 2 active + 0 historical

---

## 1. Test Domain

Test domain description.

| File | Description |
|------|-------------|
| **`TEST_SCHEMA.md`** | Test schema description. |
| **`ANOTHER_TEST_SCHEMA.md`** | Another test schema description. |

---

## 2. Another Domain

Another domain description.

| File | Description |
|------|-------------|
| **`THIRD_SCHEMA.md`** | Third schema description. |
"""


@pytest.fixture
def sample_schema_file(temp_schemas_dir: Path, sample_schema_content: str) -> Path:
    """Create a sample schema file in temp directory."""
    schema_file = temp_schemas_dir / "TEST_SCHEMA.md"
    schema_file.write_text(sample_schema_content, encoding="utf-8")
    return schema_file


@pytest.fixture
def sample_index_file(temp_schemas_dir: Path, sample_index_content: str) -> Path:
    """Create a sample SCHEMA_INDEX.md file in temp directory."""
    index_file = temp_schemas_dir / "SCHEMA_INDEX.md"
    index_file.write_text(sample_index_content, encoding="utf-8")
    return index_file


@pytest.fixture
def populated_schemas_dir(
    temp_schemas_dir: Path, sample_schema_content: str, sample_index_content: str
) -> Path:
    """Create a populated schemas directory with multiple files."""
    # Create index
    index_file = temp_schemas_dir / "SCHEMA_INDEX.md"
    index_file.write_text(sample_index_content, encoding="utf-8")

    # Create schema files
    (temp_schemas_dir / "TEST_SCHEMA.md").write_text(sample_schema_content, encoding="utf-8")
    (temp_schemas_dir / "ANOTHER_TEST_SCHEMA.md").write_text(
        "# Another Test Schema\n\nAnother test content.", encoding="utf-8"
    )
    (temp_schemas_dir / "THIRD_SCHEMA.md").write_text(
        "# Third Schema\n\nThird schema content about API design.", encoding="utf-8"
    )

    return temp_schemas_dir


@pytest.fixture
def example_schemas_dir() -> Path:
    """Get the example schemas directory from the package."""
    return Path(__file__).parent.parent / "examples" / "schemas"
