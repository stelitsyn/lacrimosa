"""Tests for schema writer functionality."""

from pathlib import Path

import pytest
from schema_mcp.tools.schema_writer import create_schema, delete_schema, update_schema
from schema_mcp.utils.errors import SchemaAlreadyExistsError, SchemaNotFoundError


class TestCreateSchema:
    """Tests for create_schema function."""

    def test_create_new_schema(self, temp_schemas_dir: Path) -> None:
        """Test creating a new schema file."""
        content = "# New Schema\n\nNew schema content."
        result = create_schema(
            "NEW_TEST_SCHEMA",
            content,
            str(temp_schemas_dir),
            add_to_index=False,
        )

        assert result["success"] is True
        assert result["schema_name"] == "NEW_TEST_SCHEMA.md"

        # Verify file exists
        schema_file = temp_schemas_dir / "NEW_TEST_SCHEMA.md"
        assert schema_file.exists()
        assert schema_file.read_text() == content

    def test_create_schema_with_index(
        self, temp_schemas_dir: Path, sample_index_file: Path
    ) -> None:
        """Test creating schema and adding to index."""
        content = "# New Schema\n\nContent."
        result = create_schema(
            "NEW_TEST_SCHEMA",
            content,
            str(temp_schemas_dir),
            domain="Test Domain",
            description="A new test schema.",
            add_to_index=True,
        )

        assert result["success"] is True
        assert result["index_updated"] is True

        # Verify index was updated
        index_content = sample_index_file.read_text()
        assert "NEW_TEST_SCHEMA.md" in index_content

    def test_create_duplicate_schema(
        self, temp_schemas_dir: Path, sample_schema_file: Path
    ) -> None:
        """Test creating a schema that already exists."""
        with pytest.raises(SchemaAlreadyExistsError):
            create_schema(
                "TEST_SCHEMA",
                "Duplicate content",
                str(temp_schemas_dir),
            )


class TestUpdateSchema:
    """Tests for update_schema function."""

    def test_update_existing_schema(self, temp_schemas_dir: Path, sample_schema_file: Path) -> None:
        """Test updating an existing schema."""
        new_content = "# Updated Schema\n\nUpdated content."
        result = update_schema(
            "TEST_SCHEMA",
            new_content,
            str(temp_schemas_dir),
        )

        assert result["success"] is True
        assert sample_schema_file.read_text() == new_content

    def test_update_with_md_extension(
        self, temp_schemas_dir: Path, sample_schema_file: Path
    ) -> None:
        """Test updating schema with .md extension in name."""
        new_content = "# Updated\n\nContent."
        result = update_schema(
            "TEST_SCHEMA.md",
            new_content,
            str(temp_schemas_dir),
        )

        assert result["success"] is True

    def test_update_nonexistent_schema(self, temp_schemas_dir: Path) -> None:
        """Test updating a schema that doesn't exist."""
        with pytest.raises(SchemaNotFoundError):
            update_schema(
                "NONEXISTENT_SCHEMA",
                "Content",
                str(temp_schemas_dir),
            )

    def test_update_index_description(
        self, temp_schemas_dir: Path, sample_schema_file: Path, sample_index_file: Path
    ) -> None:
        """Test updating schema with index description update."""
        result = update_schema(
            "TEST_SCHEMA",
            "# Updated\n\nContent.",
            str(temp_schemas_dir),
            update_index_description=True,
            new_description="Updated description.",
        )

        assert result["success"] is True
        assert result["index_updated"] is True


class TestDeleteSchema:
    """Tests for delete_schema function."""

    def test_delete_requires_confirmation(
        self, temp_schemas_dir: Path, sample_schema_file: Path
    ) -> None:
        """Test that delete requires confirmation."""
        with pytest.raises(ValueError, match="confirmation"):
            delete_schema(
                "TEST_SCHEMA",
                str(temp_schemas_dir),
                confirm=False,
            )

    def test_delete_existing_schema(self, temp_schemas_dir: Path, sample_schema_file: Path) -> None:
        """Test deleting an existing schema."""
        result = delete_schema(
            "TEST_SCHEMA",
            str(temp_schemas_dir),
            confirm=True,
        )

        assert result["success"] is True
        assert not sample_schema_file.exists()

    def test_delete_nonexistent_schema(self, temp_schemas_dir: Path) -> None:
        """Test deleting a schema that doesn't exist."""
        with pytest.raises(SchemaNotFoundError):
            delete_schema(
                "NONEXISTENT_SCHEMA",
                str(temp_schemas_dir),
                confirm=True,
            )

    def test_delete_removes_from_index(
        self, temp_schemas_dir: Path, sample_schema_file: Path, sample_index_file: Path
    ) -> None:
        """Test that delete removes schema from index."""
        result = delete_schema(
            "TEST_SCHEMA",
            str(temp_schemas_dir),
            remove_from_index=True,
            confirm=True,
        )

        assert result["success"] is True
        assert result["index_updated"] is True

        # Verify removed from index
        index_content = sample_index_file.read_text()
        assert "TEST_SCHEMA.md" not in index_content
