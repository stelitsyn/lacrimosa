"""Error handling utilities for MCP server."""

from pathlib import Path
from typing import Optional


class SchemaNotFoundError(FileNotFoundError):
    """Raised when a schema file is not found."""

    def __init__(
        self, schema_name: str, schemas_dir: Path, suggestions: Optional[list[str]] = None
    ):
        """Initialize error with schema name and suggestions."""
        self.schema_name = schema_name
        self.schemas_dir = schemas_dir
        self.suggestions = suggestions or []
        message = f"Schema '{schema_name}' not found in {schemas_dir}"
        if self.suggestions:
            message += f"\nDid you mean: {', '.join(self.suggestions[:3])}?"
        super().__init__(message)


class InvalidDomainError(ValueError):
    """Raised when an invalid domain is specified."""

    def __init__(self, domain: str, available_domains: list[str]):
        """Initialize error with domain and available domains."""
        self.domain = domain
        self.available_domains = available_domains
        message = f"Invalid domain: '{domain}'\nAvailable domains: {', '.join(available_domains)}"
        super().__init__(message)


class SchemaAlreadyExistsError(FileExistsError):
    """Raised when trying to create a schema that already exists."""

    def __init__(self, schema_name: str):
        """Initialize error with schema name."""
        self.schema_name = schema_name
        message = f"Schema '{schema_name}' already exists. Use update_schema instead."
        super().__init__(message)


def find_similar_schema_names(schema_name: str, schemas_dir: Path, limit: int = 3) -> list[str]:
    """Find similar schema names for error suggestions."""
    if not schemas_dir.exists():
        return []

    # Normalize input name
    normalized_input = schema_name.upper().replace(".MD", "").replace("_", "")

    similarities: list[tuple[str, int]] = []

    # Search in main directory
    for file_path in schemas_dir.glob("*.md"):
        if file_path.name == "SCHEMA_INDEX.md":
            continue
        file_name = file_path.stem
        normalized_file = file_name.upper().replace("_", "")

        # Simple similarity: check if normalized names share characters
        similarity_score = sum(1 for c in normalized_input if c in normalized_file)
        if similarity_score > 0:
            similarities.append((file_name, similarity_score))

    # Sort by similarity score (descending) and return top matches
    similarities.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in similarities[:limit]]
