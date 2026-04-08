"""Services for the schema MCP server."""

# EmbeddingService is optional - only available if sentence-transformers is installed
try:
    from schema_mcp.services.embedding_service import EmbeddingService

    __all__ = ["EmbeddingService"]
except ImportError:
    __all__ = []
