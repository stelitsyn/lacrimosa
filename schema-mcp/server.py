"""Main MCP server for schema management.

This server provides tools for managing schema documents organized by domain.
Schemas are markdown files following the FEATURE_NAME_SCHEMA.md naming convention.

Environment Variables:
    SCHEMAS_DIR: Path to the schemas directory (default: ./schemas relative to server.py)
"""

import json
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from schema_mcp.models.inputs import (
    KIGetInput,
    KIListInput,
    KIMGetInput,
    KISetInput,
    SchemaCreateInput,
    SchemaDeleteInput,
    SchemaDomainsInput,
    SchemaIndexInput,
    SchemaListInput,
    SchemaReadInput,
    SchemaSearchInput,
    SchemaUpdateInput,
)
from schema_mcp.tools.ki_tools import ki_get, ki_list, ki_mget, ki_set
from schema_mcp.tools.schema_index import get_schema_index, list_domains, list_schemas
from schema_mcp.tools.schema_reader import read_schema
from schema_mcp.tools.schema_search import search_schemas
from schema_mcp.tools.schema_writer import create_schema, delete_schema, update_schema

# Initialize FastMCP server
mcp = FastMCP("schema_mcp")

# Get schemas directory from environment or use default
SCHEMAS_DIR = os.getenv("SCHEMAS_DIR", str(Path(__file__).parent.parent.parent / "schemas"))


@mcp.tool(
    name="schema_read",
    annotations=ToolAnnotations(
        title="Read Schema",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def schema_read_tool(params: SchemaReadInput) -> str:
    """
    Read a specific schema file by name.

    This tool reads and returns the full content of a schema file from the project's
    schemas directory. It supports reading schemas from both the main directory and
    the historical subdirectory.

    Args:
        params (SchemaReadInput): Validated input parameters containing:
            - schema_name (str): Name of the schema file (e.g., "FEATURE_STATE_MACHINE_SCHEMA" or "FEATURE_STATE_MACHINE_SCHEMA.md")
            - include_metadata (bool): Include file metadata (size, last modified) in response

    Returns:
        str: JSON-formatted string containing schema content and metadata

    Examples:
        - Use when: "Read the feature state machine schema" -> params with schema_name="FEATURE_STATE_MACHINE_SCHEMA"
        - Use when: "Get schema file with file size" -> params with schema_name="SCHEMA_NAME", include_metadata=True
    """
    import json

    result = read_schema(params.schema_name, SCHEMAS_DIR, params.include_metadata)
    return json.dumps(result, indent=2)


@mcp.tool(
    name="schema_list",
    annotations=ToolAnnotations(
        title="List Schemas",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def schema_list_tool(params: SchemaListInput) -> str:
    """
    List all available schemas with optional filtering.

    This tool lists all schema files in the project, with optional filtering by domain,
    pagination support, and the ability to include historical schemas.

    Args:
        params (SchemaListInput): Validated input parameters containing:
            - domain (Optional[str]): Filter by domain (e.g., "User Onboarding")
            - include_historical (bool): Include historical schemas (default: False)
            - limit (int): Maximum results to return, between 1-500 (default: 100)
            - offset (int): Number of results to skip for pagination (default: 0)

    Returns:
        str: JSON-formatted string containing list of schemas with pagination info
    """
    import json

    result = list_schemas(
        SCHEMAS_DIR,
        domain=params.domain,
        include_historical=params.include_historical,
        limit=params.limit,
        offset=params.offset,
    )
    return json.dumps(result, indent=2)


@mcp.tool(
    name="schema_search",
    annotations=ToolAnnotations(
        title="Search Schemas",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def schema_search_tool(params: SchemaSearchInput) -> str:
    """
    Search schemas by keyword in content or title.

    This tool searches across all schema files for a given query string, matching
    against both file names and file content. Results include excerpts showing where
    matches were found.

    Args:
        params (SchemaSearchInput): Validated input parameters containing:
            - query (str): Search query (searches in file names and content)
            - domain (Optional[str]): Limit search to specific domain
            - case_sensitive (bool): Case-sensitive search (default: False)
            - limit (int): Maximum results to return, between 1-100 (default: 20)

    Returns:
        str: JSON-formatted string containing search results with excerpts
    """
    import json

    result = search_schemas(
        params.query,
        SCHEMAS_DIR,
        domain=params.domain,
        case_sensitive=params.case_sensitive,
        limit=params.limit,
        search_mode=params.search_mode,
    )
    return json.dumps(result, indent=2)


@mcp.tool(
    name="schema_index",
    annotations=ToolAnnotations(
        title="Get Schema Index",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def schema_index_tool(params: SchemaIndexInput) -> str:
    """
    Get the schema index organized by domain.

    This tool returns the parsed structure of SCHEMA_INDEX.md, showing how schemas
    are organized by domain with their descriptions.

    Args:
        params (SchemaIndexInput): Validated input parameters containing:
            - domain (Optional[str]): Get schemas for specific domain only
            - include_historical (bool): Include historical section (default: False)

    Returns:
        str: JSON-formatted string containing schema index structure
    """
    import json

    result = get_schema_index(
        SCHEMAS_DIR,
        domain=params.domain,
        include_historical=params.include_historical,
    )
    return json.dumps(result, indent=2)


@mcp.tool(
    name="schema_domains",
    annotations=ToolAnnotations(
        title="List Domains",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def schema_domains_tool(params: SchemaDomainsInput) -> str:
    """
    List all available domains from the schema index.

    This tool returns a list of all domains defined in SCHEMA_INDEX.md along with
    the number of schemas in each domain.

    Returns:
        str: JSON-formatted string containing list of domains with schema counts
    """
    import json

    result = list_domains(SCHEMAS_DIR)
    return json.dumps(result, indent=2)


@mcp.tool(
    name="schema_create",
    annotations=ToolAnnotations(
        title="Create Schema",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def schema_create_tool(params: SchemaCreateInput) -> str:
    """
    Create a new schema file with optional index registration.

    This tool creates a new schema file following the FEATURE_NAME_SCHEMA.md naming
    convention and optionally adds it to SCHEMA_INDEX.md in the specified domain.

    Args:
        params (SchemaCreateInput): Validated input parameters containing:
            - schema_name (str): Name of the schema file (without .md extension, must follow FEATURE_NAME_SCHEMA format)
            - content (str): Markdown content for the schema file
            - domain (Optional[str]): Domain to add schema to in index
            - description (Optional[str]): Description to add to index table (1-2 sentences)
            - add_to_index (bool): Automatically add to SCHEMA_INDEX.md (default: True)

    Returns:
        str: JSON-formatted string containing creation result and index update status

    Examples:
        - Use when: "Create a new schema for feature X" -> params with schema_name="FEATURE_X_SCHEMA", content="..."
    """
    import json

    result = create_schema(
        params.schema_name,
        params.content,
        SCHEMAS_DIR,
        domain=params.domain,
        description=params.description,
        add_to_index=params.add_to_index,
    )
    return json.dumps(result, indent=2)


@mcp.tool(
    name="schema_update",
    annotations=ToolAnnotations(
        title="Update Schema",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def schema_update_tool(params: SchemaUpdateInput) -> str:
    """
    Update an existing schema file's content.

    This tool replaces the content of an existing schema file and optionally updates
    its description in SCHEMA_INDEX.md.

    Args:
        params (SchemaUpdateInput): Validated input parameters containing:
            - schema_name (str): Name of the schema file (with or without .md extension)
            - content (str): New markdown content to replace existing content
            - update_index_description (bool): Update description in index if provided (default: False)
            - new_description (Optional[str]): New description for index (only used if update_index_description=True)

    Returns:
        str: JSON-formatted string containing update result
    """
    import json

    result = update_schema(
        params.schema_name,
        params.content,
        SCHEMAS_DIR,
        update_index_description=params.update_index_description,
        new_description=params.new_description,
    )
    return json.dumps(result, indent=2)


@mcp.tool(
    name="schema_delete",
    annotations=ToolAnnotations(
        title="Delete Schema",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def schema_delete_tool(params: SchemaDeleteInput) -> str:
    """
    Delete a schema file and optionally remove it from the index.

    This tool permanently deletes a schema file and optionally removes its entry
    from SCHEMA_INDEX.md. Deletion requires explicit confirmation.

    Args:
        params (SchemaDeleteInput): Validated input parameters containing:
            - schema_name (str): Name of the schema file to delete
            - remove_from_index (bool): Remove from SCHEMA_INDEX.md (default: True)
            - confirm (bool): Confirmation flag to prevent accidental deletion (must be True)

    Returns:
        str: JSON-formatted string containing deletion result and index update status

    Examples:
        - Use when: "Delete the test schema" -> params with schema_name="TEST_SCHEMA", confirm=True
    """
    import json

    result = delete_schema(
        params.schema_name,
        SCHEMAS_DIR,
        remove_from_index=params.remove_from_index,
        confirm=params.confirm,
    )
    return json.dumps(result, indent=2)


def _compact(payload: Any) -> str:
    """Compact JSON serialization for minimal token usage."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


@mcp.tool(
    name="ki_get",
    annotations=ToolAnnotations(
        title="KI Get Entry",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def ki_get_tool(params: KIGetInput) -> str:
    """
    Get a single Knowledge Index entry by dot-notation key (~50 tokens).

    Keys: db.us.instance, cloudrun.staging.us, gotcha.cloudflare.worker_to_worker_timeout,
    billing.system, api.endpoints, code.services.main, decision.pricing_model
    """
    result = ki_get(params.key, SCHEMAS_DIR, fuzzy=params.fuzzy)
    return _compact(result)


@mcp.tool(
    name="ki_mget",
    annotations=ToolAnnotations(
        title="KI Batch Get",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def ki_mget_tool(params: KIMGetInput) -> str:
    """
    Get multiple Knowledge Index entries in one call.

    More efficient than N separate ki_get calls — files are parsed once.
    Returns found entries + list of missing keys.
    """
    result = ki_mget(params.keys, SCHEMAS_DIR, fuzzy=params.fuzzy)
    return _compact(result)


@mcp.tool(
    name="ki_set",
    annotations=ToolAnnotations(
        title="KI Set Entry",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def ki_set_tool(params: KISetInput) -> str:
    """Upsert a single Knowledge Index entry atomically with file locking."""
    result = ki_set(
        params.key,
        params.value,
        params.source,
        SCHEMAS_DIR,
        verified=params.verified,
        extra_fields=params.extra_fields,
        section_hint=params.section_hint,
    )
    return _compact(result)


@mcp.tool(
    name="ki_list",
    annotations=ToolAnnotations(
        title="KI List Keys",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def ki_list_tool(params: KIListInput) -> str:
    """List KI keys with compact values. Filter by file or key prefix."""
    result = ki_list(
        SCHEMAS_DIR, file_filter=params.file_filter, prefix_filter=params.prefix_filter
    )
    return _compact(result)


if __name__ == "__main__":
    # Run the server
    mcp.run()
