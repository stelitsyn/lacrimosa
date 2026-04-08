"""Schema create/update/delete operations."""

import re
from pathlib import Path
from typing import Any, Optional

from schema_mcp.utils.errors import (
    SchemaAlreadyExistsError,
    SchemaNotFoundError,
    find_similar_schema_names,
)


def create_schema(
    schema_name: str,
    content: str,
    schemas_dir: str,
    domain: Optional[str] = None,
    description: Optional[str] = None,
    add_to_index: bool = True,
) -> dict[str, Any]:
    """
    Create a new schema file with optional index registration.

    Args:
        schema_name: Name of the schema file (without .md extension)
        content: Markdown content for the schema file
        schemas_dir: Path to the schemas directory
        domain: Domain to add schema to in index
        description: Description to add to index table
        add_to_index: Automatically add to SCHEMA_INDEX.md

    Returns:
        Dictionary with creation result and index update status

    Raises:
        SchemaAlreadyExistsError: If schema already exists
    """
    schemas_path = Path(schemas_dir)
    schema_file = schemas_path / f"{schema_name}.md"

    # Check if file already exists
    if schema_file.exists():
        raise SchemaAlreadyExistsError(schema_name)

    try:
        # Write schema file
        schema_file.write_text(content, encoding="utf-8")

        index_updated = False
        if add_to_index and domain:
            # Update index
            index_updated = _add_schema_to_index(
                schemas_path, schema_name, domain, description or ""
            )

        return {
            "success": True,
            "schema_name": f"{schema_name}.md",
            "file_path": str(schema_file),
            "index_updated": index_updated,
        }
    except Exception:
        # Rollback: delete file if index update fails
        if schema_file.exists():
            schema_file.unlink()
        raise


def update_schema(
    schema_name: str,
    content: str,
    schemas_dir: str,
    update_index_description: bool = False,
    new_description: Optional[str] = None,
) -> dict[str, Any]:
    """
    Update an existing schema file's content.

    Args:
        schema_name: Name of the schema file (with or without .md extension)
        content: New markdown content to replace existing content
        schemas_dir: Path to the schemas directory
        update_index_description: Update description in index if provided
        new_description: New description for index

    Returns:
        Dictionary with update result

    Raises:
        SchemaNotFoundError: If schema file is not found
    """
    schemas_path = Path(schemas_dir)

    # Normalize schema name
    normalized_name = schema_name.removesuffix(".md")
    schema_file = schemas_path / f"{normalized_name}.md"

    if not schema_file.exists():
        suggestions = find_similar_schema_names(schema_name, schemas_path)
        raise SchemaNotFoundError(schema_name, schemas_path, suggestions)

    # Write updated content
    schema_file.write_text(content, encoding="utf-8")

    index_updated = False
    if update_index_description and new_description:
        index_updated = _update_schema_in_index(schemas_path, normalized_name, new_description)

    return {
        "success": True,
        "schema_name": f"{normalized_name}.md",
        "file_path": str(schema_file),
        "index_updated": index_updated,
    }


def delete_schema(
    schema_name: str,
    schemas_dir: str,
    remove_from_index: bool = True,
    confirm: bool = False,
) -> dict[str, Any]:
    """
    Delete a schema file and optionally remove it from the index.

    Args:
        schema_name: Name of the schema file to delete
        schemas_dir: Path to the schemas directory
        remove_from_index: Remove from SCHEMA_INDEX.md
        confirm: Confirmation flag (must be True to proceed)

    Returns:
        Dictionary with deletion result

    Raises:
        ValueError: If confirm is not True
        SchemaNotFoundError: If schema file is not found
    """
    if not confirm:
        raise ValueError("Deletion requires explicit confirmation. Set confirm=True to proceed.")

    schemas_path = Path(schemas_dir)

    # Normalize schema name
    normalized_name = schema_name.removesuffix(".md")
    schema_file = schemas_path / f"{normalized_name}.md"

    if not schema_file.exists():
        suggestions = find_similar_schema_names(schema_name, schemas_path)
        raise SchemaNotFoundError(schema_name, schemas_path, suggestions)

    # Delete file
    schema_file.unlink()

    index_updated = False
    if remove_from_index:
        index_updated = _remove_schema_from_index(schemas_path, normalized_name)

    return {
        "success": True,
        "schema_name": f"{normalized_name}.md",
        "index_updated": index_updated,
    }


def _add_schema_to_index(
    schemas_path: Path, schema_name: str, domain: str, description: str
) -> bool:
    """Add schema to SCHEMA_INDEX.md in the specified domain."""
    index_file = schemas_path / "SCHEMA_INDEX.md"
    if not index_file.exists():
        return False

    content = index_file.read_text(encoding="utf-8")

    # Find domain section
    domain_pattern = rf"##\s*\d+\.\s*{re.escape(domain)}\s*\n\n"
    domain_match = re.search(domain_pattern, content)

    if not domain_match:
        return False

    # Find the table in this domain section
    domain_start = domain_match.end()
    # Find the end of this domain section (next ## or ---)
    domain_end_match = re.search(r"\n---|\n##\s*\d+\.", content[domain_start:])
    domain_end = domain_start + (domain_end_match.start() if domain_end_match else len(content))

    domain_section = content[domain_start:domain_end]

    # Check if schema already in table
    if f"**`{schema_name}.md`**" in domain_section:
        return False

    # Find the table and add new row
    table_pattern = r"(\| File \| Description \|\n\|------\|\s*------\|\n)"
    table_match = re.search(table_pattern, domain_section)

    if table_match:
        # Add new row after table header
        new_row = f"| **`{schema_name}.md`** | {description} |\n"
        insert_pos = domain_start + table_match.end()
        content = content[:insert_pos] + new_row + content[insert_pos:]
    else:
        # Create table if it doesn't exist
        table_header = "| File | Description |\n|------|-------------|\n"
        new_row = f"| **`{schema_name}.md`** | {description} |\n"
        insert_pos = domain_start
        content = content[:insert_pos] + table_header + new_row + content[insert_pos:]

    index_file.write_text(content, encoding="utf-8")
    return True


def _update_schema_in_index(schemas_path: Path, schema_name: str, new_description: str) -> bool:
    """Update schema description in SCHEMA_INDEX.md."""
    index_file = schemas_path / "SCHEMA_INDEX.md"
    if not index_file.exists():
        return False

    content = index_file.read_text(encoding="utf-8")

    # Find and replace schema description
    pattern = rf"\*\*`{re.escape(schema_name)}\.md`\*\*\s*\|\s*[^\n]+"
    replacement = f"**`{schema_name}.md`** | {new_description}"

    if re.search(pattern, content):
        content = re.sub(pattern, replacement, content)
        index_file.write_text(content, encoding="utf-8")
        return True

    return False


def _remove_schema_from_index(schemas_path: Path, schema_name: str) -> bool:
    """Remove schema from SCHEMA_INDEX.md."""
    index_file = schemas_path / "SCHEMA_INDEX.md"
    if not index_file.exists():
        return False

    content = index_file.read_text(encoding="utf-8")

    # Find and remove schema row
    pattern = rf"\*\*`{re.escape(schema_name)}\.md`\*\*\s*\|\s*[^\n]+\n"
    if re.search(pattern, content):
        content = re.sub(pattern, "", content)
        index_file.write_text(content, encoding="utf-8")
        return True

    return False
