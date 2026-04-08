# Schema MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for managing schema documents with semantic search capabilities. Organize, search, and manage your project's schema documentation through AI assistants like Claude.

## Features

- **8 MCP Tools** for comprehensive schema management:
  - `schema_read` - Read schema files with optional metadata
  - `schema_list` - List schemas with filtering and pagination
  - `schema_search` - Search with keyword, semantic, or hybrid modes
  - `schema_index` - Get domain-organized schema structure
  - `schema_domains` - List all available domains
  - `schema_create` - Create new schema files
  - `schema_update` - Update existing schemas
  - `schema_delete` - Delete schemas (with confirmation)

- **Three Search Modes**:
  - **Keyword**: Fast lexical matching with exact phrase, AND, and OR logic
  - **Semantic**: AI-powered similarity search using sentence-transformers
  - **Hybrid** (default): Combined scoring (70% semantic + 30% keyword)

- **Domain Organization**: Group schemas by domain with automatic index management
- **Embedding Cache**: Automatic caching of semantic embeddings for fast searches
- **Type-Safe**: Full Pydantic validation for all inputs

## Installation

### Basic Installation

```bash
pip install schema-mcp
```

### With Semantic Search (Recommended)

```bash
pip install schema-mcp[semantic]
```

### Development Installation

```bash
pip install schema-mcp[all]
```

## Quick Start

### 1. Create Your Schemas Directory

Create a `schemas/` directory in your project with your schema files:

```
schemas/
├── SCHEMA_INDEX.md          # Index file (auto-managed)
├── USER_AUTH_SCHEMA.md      # Your schema files
├── API_DESIGN_SCHEMA.md
└── DATABASE_SCHEMA.md
```

### 2. Create SCHEMA_INDEX.md

Create an index file to organize schemas by domain:

```markdown
# Schema Index

**Last Updated**: 2024-01-15
**Total Schemas**: 3 active + 0 historical

---

## 1. Authentication

Authentication and authorization schemas.

| File | Description |
|------|-------------|
| **`USER_AUTH_SCHEMA.md`** | User authentication flow and session management. |

---

## 2. API Design

API design patterns and conventions.

| File | Description |
|------|-------------|
| **`API_DESIGN_SCHEMA.md`** | REST API design guidelines. |

---

## 3. Database

Database schema definitions.

| File | Description |
|------|-------------|
| **`DATABASE_SCHEMA.md`** | Database tables and relationships. |
```

### 3. Configure MCP Client

Add the server to your MCP client configuration (e.g., Claude Desktop):

#### Option A: Using pip-installed package

```json
{
  "mcpServers": {
    "schema-mcp": {
      "command": "schema-mcp",
      "env": {
        "SCHEMAS_DIR": "/path/to/your/project/schemas"
      }
    }
  }
}
```

#### Option B: Using Python directly

```json
{
  "mcpServers": {
    "schema-mcp": {
      "command": "python",
      "args": ["-m", "schema_mcp"],
      "env": {
        "PYTHONPATH": "/path/to/schema-mcp-package/src",
        "SCHEMAS_DIR": "/path/to/your/project/schemas"
      }
    }
  }
}
```

## Usage Examples

Once configured, your AI assistant can use these tools:

### Reading Schemas

```
"Read the user authentication schema"
→ schema_read(schema_name="USER_AUTH_SCHEMA")
```

### Searching Schemas

```
"Search for schemas about database migrations"
→ schema_search(query="database migrations", search_mode="hybrid")
```

### Listing by Domain

```
"Show all schemas in the API Design domain"
→ schema_list(domain="API Design")
```

### Creating Schemas

```
"Create a new schema for payment processing"
→ schema_create(
    schema_name="PAYMENT_PROCESSING_SCHEMA",
    content="# Payment Processing\n\n...",
    domain="Payments",
    description="Payment gateway integration patterns."
)
```

## Schema Naming Convention

Schema files must follow the pattern: `FEATURE_NAME_SCHEMA.md`

- **Uppercase** with underscores
- Must end with `_SCHEMA`
- Extension: `.md`

Examples:
- ✅ `USER_AUTH_SCHEMA.md`
- ✅ `API_RATE_LIMITING_SCHEMA.md`
- ❌ `user-auth-schema.md`
- ❌ `ApiSchema.md`

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SCHEMAS_DIR` | Path to your schemas directory | `./schemas` (relative to server.py) |

## API Reference

### schema_read

Read a specific schema file by name.

**Parameters:**
- `schema_name` (str): Name of the schema file (with or without `.md`)
- `include_metadata` (bool, optional): Include file size and modified time. Default: `false`

**Returns:** Schema content and optional metadata

### schema_list

List all available schemas with optional filtering.

**Parameters:**
- `domain` (str, optional): Filter by domain name
- `include_historical` (bool, optional): Include archived schemas. Default: `false`
- `limit` (int, optional): Max results (1-500). Default: `100`
- `offset` (int, optional): Pagination offset. Default: `0`

**Returns:** List of schemas with pagination info

### schema_search

Search schemas by keyword and/or semantic similarity.

**Parameters:**
- `query` (str): Search query
- `domain` (str, optional): Limit search to specific domain
- `case_sensitive` (bool, optional): Case-sensitive search. Default: `false`
- `limit` (int, optional): Max results (1-100). Default: `20`
- `search_mode` (str, optional): `keyword`, `semantic`, or `hybrid`. Default: `hybrid`

**Returns:** Matching schemas with excerpts and relevance scores

### schema_index

Get the schema index organized by domain.

**Parameters:**
- `domain` (str, optional): Get schemas for specific domain only
- `include_historical` (bool, optional): Include historical section. Default: `false`

**Returns:** Parsed index structure with domains and schemas

### schema_domains

List all available domains from the schema index.

**Parameters:** None

**Returns:** List of domains with schema counts

### schema_create

Create a new schema file with optional index registration.

**Parameters:**
- `schema_name` (str): Name following `FEATURE_NAME_SCHEMA` convention
- `content` (str): Markdown content for the schema
- `domain` (str, optional): Domain to add schema to in index
- `description` (str, optional): Description for index table
- `add_to_index` (bool, optional): Auto-add to SCHEMA_INDEX.md. Default: `true`

**Returns:** Creation result and index update status

### schema_update

Update an existing schema file's content.

**Parameters:**
- `schema_name` (str): Name of the schema file
- `content` (str): New markdown content
- `update_index_description` (bool, optional): Update index description. Default: `false`
- `new_description` (str, optional): New description for index

**Returns:** Update result

### schema_delete

Delete a schema file (requires explicit confirmation).

**Parameters:**
- `schema_name` (str): Name of the schema file to delete
- `remove_from_index` (bool, optional): Remove from SCHEMA_INDEX.md. Default: `true`
- `confirm` (bool): Must be `true` to proceed

**Returns:** Deletion result

## Semantic Search

When installed with `[semantic]` extras, the server uses [sentence-transformers](https://www.sbert.net/) for AI-powered search:

- **Model**: `all-MiniLM-L6-v2` (384 dimensions, ~80MB)
- **Caching**: Embeddings cached in `.embeddings_cache.json`
- **Fallback**: Gracefully falls back to keyword search if not installed

### Cache Management

The embedding cache is automatically managed:
- Cache is invalidated when schema content changes (MD5 hash comparison)
- Cache version is checked on load
- Force rebuild with `embed_documents(force_rebuild=True)`

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[all]"

# Run tests
pytest

# Run with coverage
pytest --cov=schema_mcp
```

### Type Checking

```bash
mypy src/schema_mcp
```

### Linting

```bash
ruff check src/
ruff format src/
```

## Project Structure

```
schema-mcp/
├── src/schema_mcp/
│   ├── __init__.py
│   ├── __main__.py          # Entry point
│   ├── server.py             # MCP server with tool definitions
│   ├── models/
│   │   └── inputs.py         # Pydantic input models
│   ├── tools/
│   │   ├── schema_reader.py  # Read operations
│   │   ├── schema_search.py  # Search logic
│   │   ├── schema_index.py   # Index parsing
│   │   └── schema_writer.py  # Write operations
│   ├── services/
│   │   └── embedding_service.py  # Semantic search
│   └── utils/
│       └── errors.py         # Custom exceptions
├── tests/
├── examples/
│   └── schemas/              # Sample schemas
├── pyproject.toml
└── README.md
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- Built with [FastMCP](https://github.com/anthropics/mcp) by Anthropic
- Semantic search powered by [sentence-transformers](https://www.sbert.net/)
