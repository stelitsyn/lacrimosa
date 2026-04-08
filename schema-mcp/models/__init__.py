"""Pydantic models for MCP tool inputs."""

from schema_mcp.models.inputs import (
    SchemaCreateInput,
    SchemaDeleteInput,
    SchemaDomainsInput,
    SchemaIndexInput,
    SchemaListInput,
    SchemaReadInput,
    SchemaSearchInput,
    SchemaUpdateInput,
)

__all__ = [
    "SchemaReadInput",
    "SchemaListInput",
    "SchemaSearchInput",
    "SchemaIndexInput",
    "SchemaCreateInput",
    "SchemaUpdateInput",
    "SchemaDeleteInput",
    "SchemaDomainsInput",
]
