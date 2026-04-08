"""Tests for schema reader functionality."""

from pathlib import Path

import pytest
from schema_mcp.tools.schema_reader import read_schema
from schema_mcp.utils.errors import SchemaNotFoundError


class TestReadSchema:
    """Tests for read_schema function."""

    def test_read_existing_schema(
        self, temp_schemas_dir: Path, sample_schema_file: Path, sample_schema_content: str
    ) -> None:
        """Test reading an existing schema file."""
        result = read_schema("TEST_SCHEMA", str(temp_schemas_dir))

        assert result["schema_name"] == "TEST_SCHEMA.md"
        assert result["content"] == sample_schema_content
        assert "metadata" not in result

    def test_read_schema_with_md_extension(
        self, temp_schemas_dir: Path, sample_schema_file: Path
    ) -> None:
        """Test reading schema when .md extension is included."""
        result = read_schema("TEST_SCHEMA.md", str(temp_schemas_dir))
        assert result["schema_name"] == "TEST_SCHEMA.md"

    def test_read_schema_with_metadata(
        self, temp_schemas_dir: Path, sample_schema_file: Path
    ) -> None:
        """Test reading schema with metadata included."""
        result = read_schema("TEST_SCHEMA", str(temp_schemas_dir), include_metadata=True)

        assert "metadata" in result
        assert "size" in result["metadata"]
        assert "modified" in result["metadata"]
        assert result["metadata"]["size"] > 0

    def test_read_nonexistent_schema(self, temp_schemas_dir: Path) -> None:
        """Test reading a schema that doesn't exist."""
        with pytest.raises(SchemaNotFoundError) as exc_info:
            read_schema("NONEXISTENT_SCHEMA", str(temp_schemas_dir))

        assert "NONEXISTENT_SCHEMA" in str(exc_info.value)

    def test_read_schema_from_historical(self, temp_schemas_dir: Path) -> None:
        """Test reading schema from historical subdirectory."""
        # Create historical directory and file
        historical_dir = temp_schemas_dir / "historical"
        historical_dir.mkdir()
        historical_file = historical_dir / "OLD_SCHEMA.md"
        historical_file.write_text("# Old Schema\n\nHistorical content.", encoding="utf-8")

        result = read_schema("OLD_SCHEMA", str(temp_schemas_dir))

        assert result["schema_name"] == "historical/OLD_SCHEMA.md"
        assert "Historical content" in result["content"]

    def test_error_includes_suggestions(
        self, temp_schemas_dir: Path, sample_schema_file: Path
    ) -> None:
        """Test that error includes similar schema name suggestions."""
        with pytest.raises(SchemaNotFoundError) as exc_info:
            read_schema("TSET_SCHEMA", str(temp_schemas_dir))  # Typo

        # Should suggest TEST_SCHEMA
        assert exc_info.value.suggestions is not None
        assert len(exc_info.value.suggestions) > 0
