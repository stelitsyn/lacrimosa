"""Schema index parsing and domain queries."""

import re
from pathlib import Path
from typing import Any, Optional


def parse_index(schemas_dir: str) -> dict[str, Any]:
    """
    Parse SCHEMA_INDEX.md to extract domain organization.

    Args:
        schemas_dir: Path to the schemas directory

    Returns:
        Dictionary with parsed index data including domains and schemas
    """
    schemas_path = Path(schemas_dir)
    index_file = schemas_path / "SCHEMA_INDEX.md"

    if not index_file.exists():
        return {"domains": [], "total_schemas": 0, "last_updated": None}

    content = index_file.read_text(encoding="utf-8")

    # Extract last updated date
    last_updated_match = re.search(r"\*\*Last Updated\*\*:\s*(\d{4}-\d{2}-\d{2})", content)
    last_updated = last_updated_match.group(1) if last_updated_match else None

    # Extract total schemas
    total_match = re.search(r"\*\*Total Schemas\*\*:\s*(\d+)\s*active", content)
    total_schemas = int(total_match.group(1)) if total_match else 0

    # Parse domains
    domains: list[dict[str, Any]] = []
    domain_pattern = r"##\s*\d+\.\s*(.+?)\n\n(.+?)(?=\n---|\n##\s*\d+\.|$)"

    for match in re.finditer(domain_pattern, content, re.DOTALL):
        domain_name = match.group(1).strip()
        domain_section = match.group(2)

        # Extract domain description (first paragraph)
        desc_match = re.search(r"^(.+?)(?=\n\n|$)", domain_section, re.MULTILINE)
        description = desc_match.group(1).strip() if desc_match else ""

        # Parse schema table
        schemas: list[dict[str, Any]] = []
        table_pattern = r"\*\*`([^`]+)`\*\*\s*\|\s*(.+?)(?=\n\||$)"

        for table_match in re.finditer(table_pattern, domain_section, re.MULTILINE):
            schema_file = table_match.group(1).strip()
            schema_desc = table_match.group(2).strip()
            schemas.append({"file": schema_file, "description": schema_desc})

        domains.append(
            {
                "name": domain_name,
                "description": description,
                "schemas": schemas,
                "count": len(schemas),
            }
        )

    return {
        "domains": domains,
        "total_schemas": total_schemas,
        "last_updated": last_updated,
    }


def get_schema_index(
    schemas_dir: str,
    domain: Optional[str] = None,
    include_historical: bool = False,
) -> dict[str, Any]:
    """
    Get the schema index organized by domain.

    Args:
        schemas_dir: Path to the schemas directory
        domain: Optional domain filter
        include_historical: Include historical section

    Returns:
        Dictionary with schema index structure
    """
    index_data = parse_index(schemas_dir)

    # Filter by domain if specified
    if domain:
        filtered_domains = [d for d in index_data["domains"] if d["name"] == domain]
        index_data["domains"] = filtered_domains

    # Note: Historical section parsing would be added here if needed
    # For now, we just return the parsed index

    return index_data


def list_schemas(
    schemas_dir: str,
    domain: Optional[str] = None,
    include_historical: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """
    List all available schemas with optional filtering.

    Args:
        schemas_dir: Path to the schemas directory
        domain: Optional domain filter
        include_historical: Include historical schemas
        limit: Maximum results to return
        offset: Pagination offset

    Returns:
        Dictionary with list of schemas and pagination info
    """
    schemas_path = Path(schemas_dir)
    all_schemas: list[dict[str, Any]] = []

    # Get schemas from index if available
    index_data = parse_index(schemas_dir)
    domain_schemas_map: dict[str, list[str]] = {}

    for domain_data in index_data["domains"]:
        domain_name = domain_data["name"]
        for schema_info in domain_data["schemas"]:
            schema_file = schema_info["file"].removesuffix(".md")
            if domain_name not in domain_schemas_map:
                domain_schemas_map[domain_name] = []
            domain_schemas_map[domain_name].append(schema_file)

    # Also scan filesystem for schemas not in index
    for schema_file in schemas_path.glob("*.md"):
        if schema_file.name == "SCHEMA_INDEX.md":
            continue
        schema_name = schema_file.stem
        # Find domain from index
        schema_domain = None
        for dom_name, schemas_list in domain_schemas_map.items():
            if schema_name in schemas_list:
                schema_domain = dom_name
                break

        all_schemas.append(
            {
                "name": schema_file.name,
                "domain": schema_domain,
                "description": None,  # Would need to look up from index
            }
        )

    # Add historical schemas if requested
    if include_historical:
        historical_dir = schemas_path / "historical"
        if historical_dir.exists():
            for schema_file in historical_dir.glob("*.md"):
                all_schemas.append(
                    {
                        "name": f"historical/{schema_file.name}",
                        "domain": "Historical",
                        "description": None,
                    }
                )

    # Filter by domain if specified
    if domain:
        all_schemas = [s for s in all_schemas if s.get("domain") == domain]

    # Apply pagination
    total = len(all_schemas)
    paginated_schemas = all_schemas[offset : offset + limit]

    return {
        "schemas": paginated_schemas,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(paginated_schemas) < total,
    }


def list_domains(schemas_dir: str) -> dict[str, Any]:
    """
    List all available domains from the schema index.

    Args:
        schemas_dir: Path to the schemas directory

    Returns:
        Dictionary with list of domains and their schema counts
    """
    index_data = parse_index(schemas_dir)

    domains_list = [
        {
            "name": domain["name"],
            "count": domain["count"],
            "description": domain["description"],
        }
        for domain in index_data["domains"]
    ]

    return {"domains": domains_list, "total_domains": len(domains_list)}
