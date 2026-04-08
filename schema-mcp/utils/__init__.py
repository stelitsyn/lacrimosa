"""Utility functions and error classes for the schema MCP server."""

from schema_mcp.utils.errors import (
    InvalidDomainError,
    SchemaAlreadyExistsError,
    SchemaNotFoundError,
    find_similar_schema_names,
)

__all__ = [
    "SchemaNotFoundError",
    "InvalidDomainError",
    "SchemaAlreadyExistsError",
    "find_similar_schema_names",
]
