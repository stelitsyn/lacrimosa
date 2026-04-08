"""Schema reading functionality."""

from pathlib import Path
from typing import Any

from schema_mcp.utils.errors import SchemaNotFoundError, find_similar_schema_names


def read_schema(
    schema_name: str,
    schemas_dir: str,
    include_metadata: bool = False,
) -> dict[str, Any]:
    """
    Read a specific schema file by name.

    Args:
        schema_name: Name of the schema file (with or without .md extension)
        schemas_dir: Path to the schemas directory
        include_metadata: Include file metadata (size, last modified) in response

    Returns:
        Dictionary with schema content and metadata

    Raises:
        SchemaNotFoundError: If schema file is not found
    """
    schemas_path = Path(schemas_dir)

    # Normalize schema name (remove .md if present, then add it back)
    normalized_name = schema_name.removesuffix(".md")
    schema_file = schemas_path / f"{normalized_name}.md"

    # Check if file exists
    if not schema_file.exists():
        # Check in historical subdirectory
        historical_file = schemas_path / "historical" / f"{normalized_name}.md"
        if historical_file.exists():
            schema_file = historical_file
        else:
            # Find similar names for error message
            suggestions = find_similar_schema_names(schema_name, schemas_path)
            raise SchemaNotFoundError(schema_name, schemas_path, suggestions)

    # Read file content
    content = schema_file.read_text(encoding="utf-8")

    result: dict[str, Any] = {
        "schema_name": (
            schema_file.name
            if schema_file.parent == schemas_path
            else f"{schema_file.parent.name}/{schema_file.name}"
        ),
        "content": content,
    }

    if include_metadata:
        stat = schema_file.stat()
        result["metadata"] = {
            "size": stat.st_size,
            "modified": stat.st_mtime,
        }

    return result
