"""Tests for schema index parsing and queries."""

from pathlib import Path

from schema_mcp.tools.schema_index import (
    get_schema_index,
    list_domains,
    list_schemas,
    parse_index,
)


class TestParseIndex:
    """Tests for parse_index function."""

    def test_parse_valid_index(self, temp_schemas_dir: Path, sample_index_file: Path) -> None:
        """Test parsing a valid SCHEMA_INDEX.md file."""
        result = parse_index(str(temp_schemas_dir))

        assert result["total_schemas"] == 2
        assert result["last_updated"] == "2025-01-01"
        assert len(result["domains"]) == 2

    def test_parse_domain_structure(self, temp_schemas_dir: Path, sample_index_file: Path) -> None:
        """Test domain structure in parsed index."""
        result = parse_index(str(temp_schemas_dir))

        first_domain = result["domains"][0]
        assert first_domain["name"] == "Test Domain"
        assert first_domain["count"] == 2
        assert len(first_domain["schemas"]) == 2

    def test_parse_schema_entries(self, temp_schemas_dir: Path, sample_index_file: Path) -> None:
        """Test schema entries in parsed index."""
        result = parse_index(str(temp_schemas_dir))

        first_schema = result["domains"][0]["schemas"][0]
        assert first_schema["file"] == "TEST_SCHEMA.md"
        assert "description" in first_schema

    def test_parse_missing_index(self, temp_schemas_dir: Path) -> None:
        """Test parsing when index file doesn't exist."""
        result = parse_index(str(temp_schemas_dir))

        assert result["domains"] == []
        assert result["total_schemas"] == 0
        assert result["last_updated"] is None


class TestGetSchemaIndex:
    """Tests for get_schema_index function."""

    def test_get_full_index(self, temp_schemas_dir: Path, sample_index_file: Path) -> None:
        """Test getting full schema index."""
        result = get_schema_index(str(temp_schemas_dir))

        assert "domains" in result
        assert len(result["domains"]) == 2

    def test_filter_by_domain(self, temp_schemas_dir: Path, sample_index_file: Path) -> None:
        """Test filtering index by domain."""
        result = get_schema_index(str(temp_schemas_dir), domain="Test Domain")

        assert len(result["domains"]) == 1
        assert result["domains"][0]["name"] == "Test Domain"

    def test_filter_nonexistent_domain(
        self, temp_schemas_dir: Path, sample_index_file: Path
    ) -> None:
        """Test filtering by domain that doesn't exist."""
        result = get_schema_index(str(temp_schemas_dir), domain="Nonexistent")

        assert len(result["domains"]) == 0


class TestListSchemas:
    """Tests for list_schemas function."""

    def test_list_all_schemas(self, populated_schemas_dir: Path) -> None:
        """Test listing all schemas."""
        result = list_schemas(str(populated_schemas_dir))

        assert result["total"] >= 3  # At least 3 schema files
        assert len(result["schemas"]) >= 3

    def test_pagination_limit(self, populated_schemas_dir: Path) -> None:
        """Test pagination with limit."""
        result = list_schemas(str(populated_schemas_dir), limit=2)

        assert len(result["schemas"]) <= 2
        assert result["limit"] == 2

    def test_pagination_offset(self, populated_schemas_dir: Path) -> None:
        """Test pagination with offset."""
        result_no_offset = list_schemas(str(populated_schemas_dir), limit=100)
        result_with_offset = list_schemas(str(populated_schemas_dir), offset=1, limit=100)

        assert result_with_offset["offset"] == 1
        assert result_with_offset["total"] == result_no_offset["total"]
        assert len(result_with_offset["schemas"]) == len(result_no_offset["schemas"]) - 1

    def test_filter_by_domain(self, populated_schemas_dir: Path) -> None:
        """Test filtering schemas by domain."""
        result = list_schemas(str(populated_schemas_dir), domain="Test Domain")

        for schema in result["schemas"]:
            assert schema["domain"] == "Test Domain"

    def test_has_more_flag(self, populated_schemas_dir: Path) -> None:
        """Test has_more pagination flag."""
        result = list_schemas(str(populated_schemas_dir), limit=1)

        if result["total"] > 1:
            assert result["has_more"] is True


class TestListDomains:
    """Tests for list_domains function."""

    def test_list_all_domains(self, temp_schemas_dir: Path, sample_index_file: Path) -> None:
        """Test listing all domains."""
        result = list_domains(str(temp_schemas_dir))

        assert result["total_domains"] == 2
        assert len(result["domains"]) == 2

    def test_domain_info_structure(self, temp_schemas_dir: Path, sample_index_file: Path) -> None:
        """Test domain info structure."""
        result = list_domains(str(temp_schemas_dir))

        domain = result["domains"][0]
        assert "name" in domain
        assert "count" in domain
        assert "description" in domain

    def test_empty_index(self, temp_schemas_dir: Path) -> None:
        """Test listing domains when no index exists."""
        result = list_domains(str(temp_schemas_dir))

        assert result["total_domains"] == 0
        assert result["domains"] == []
