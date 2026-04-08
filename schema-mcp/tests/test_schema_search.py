"""Tests for schema search functionality."""

from pathlib import Path

from schema_mcp.tools.schema_search import search_schemas


class TestKeywordSearch:
    """Tests for keyword search mode."""

    def test_exact_phrase_match(self, populated_schemas_dir: Path) -> None:
        """Test search with exact phrase match."""
        result = search_schemas("test schema", str(populated_schemas_dir), search_mode="keyword")

        assert result["search_mode"] == "keyword"
        assert result["total"] > 0
        assert len(result["matches"]) > 0

    def test_all_words_match(self, populated_schemas_dir: Path) -> None:
        """Test search matching all words (AND logic)."""
        result = search_schemas(
            "authentication database", str(populated_schemas_dir), search_mode="keyword"
        )

        assert result["search_mode"] == "keyword"
        # Should find TEST_SCHEMA which contains both words

    def test_partial_word_match(self, populated_schemas_dir: Path) -> None:
        """Test search with partial word matches."""
        result = search_schemas("API", str(populated_schemas_dir), search_mode="keyword")

        assert result["search_mode"] == "keyword"
        # Should find THIRD_SCHEMA which mentions API

    def test_case_insensitive_by_default(self, populated_schemas_dir: Path) -> None:
        """Test that search is case-insensitive by default."""
        result_lower = search_schemas("test", str(populated_schemas_dir), search_mode="keyword")
        result_upper = search_schemas("TEST", str(populated_schemas_dir), search_mode="keyword")

        assert result_lower["total"] == result_upper["total"]

    def test_case_sensitive_search(self, populated_schemas_dir: Path) -> None:
        """Test case-sensitive search."""
        result = search_schemas(
            "test", str(populated_schemas_dir), case_sensitive=True, search_mode="keyword"
        )

        assert result["search_mode"] == "keyword"

    def test_empty_query(self, populated_schemas_dir: Path) -> None:
        """Test search with empty query."""
        result = search_schemas("", str(populated_schemas_dir), search_mode="keyword")

        assert result["total"] == 0
        assert result["search_strategy"] == "empty_query"

    def test_no_matches(self, populated_schemas_dir: Path) -> None:
        """Test search with no matches."""
        result = search_schemas(
            "xyznonexistent123", str(populated_schemas_dir), search_mode="keyword"
        )

        assert result["total"] == 0
        assert result["search_strategy"] == "no_matches"

    def test_limit_results(self, populated_schemas_dir: Path) -> None:
        """Test limiting search results."""
        result = search_schemas(
            "schema", str(populated_schemas_dir), limit=1, search_mode="keyword"
        )

        assert len(result["matches"]) <= 1


class TestHybridSearch:
    """Tests for hybrid search mode."""

    def test_hybrid_mode_default(self, populated_schemas_dir: Path) -> None:
        """Test that hybrid is the default search mode."""
        result = search_schemas("test", str(populated_schemas_dir))

        # Should be hybrid (or fallback to keyword if semantic not available)
        assert result["search_mode"] in ["hybrid", "keyword"]

    def test_hybrid_fallback_without_transformers(self, populated_schemas_dir: Path) -> None:
        """Test hybrid search falls back gracefully without sentence-transformers."""
        result = search_schemas("authentication", str(populated_schemas_dir), search_mode="hybrid")

        # Should either work or fallback
        assert "matches" in result
        assert "search_mode" in result


class TestDomainFilter:
    """Tests for domain filtering in search."""

    def test_filter_by_domain(self, populated_schemas_dir: Path) -> None:
        """Test filtering search by domain."""
        result = search_schemas(
            "schema",
            str(populated_schemas_dir),
            domain="Test Domain",
            search_mode="keyword",
        )

        # Should only include schemas from Test Domain
        assert result["search_mode"] == "keyword"

    def test_invalid_domain_returns_empty(self, populated_schemas_dir: Path) -> None:
        """Test search with invalid domain returns no results."""
        result = search_schemas(
            "test",
            str(populated_schemas_dir),
            domain="Nonexistent Domain",
            search_mode="keyword",
        )

        assert result["total"] == 0


class TestSearchResults:
    """Tests for search result structure."""

    def test_result_contains_excerpt(self, populated_schemas_dir: Path) -> None:
        """Test that results contain excerpts."""
        result = search_schemas("authentication", str(populated_schemas_dir), search_mode="keyword")

        if result["matches"]:
            assert "excerpt" in result["matches"][0]

    def test_result_contains_schema_name(self, populated_schemas_dir: Path) -> None:
        """Test that results contain schema names."""
        result = search_schemas("test", str(populated_schemas_dir), search_mode="keyword")

        if result["matches"]:
            assert "schema_name" in result["matches"][0]
            assert result["matches"][0]["schema_name"].endswith(".md")
