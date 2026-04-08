"""Pydantic input models for MCP tool inputs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SchemaReadInput(BaseModel):
    """Input model for schema_read tool."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    schema_name: str = Field(
        ..., description="Name of the schema file (with or without .md extension)", min_length=1
    )
    include_metadata: bool = Field(
        default=False, description="Include file metadata (size, last modified) in response"
    )


class SchemaListInput(BaseModel):
    """Input model for schema_list tool."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    domain: str | None = Field(
        default=None, description="Filter by domain (e.g., 'User Onboarding')"
    )
    include_historical: bool = Field(default=False, description="Include historical schemas")
    limit: int = Field(default=100, description="Maximum results to return", ge=1, le=500)
    offset: int = Field(default=0, description="Number of results to skip for pagination", ge=0)


class SchemaSearchInput(BaseModel):
    """Input model for schema_search tool."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    query: str = Field(
        ..., description="Search query (searches in file names and content)", min_length=1
    )
    domain: str | None = Field(default=None, description="Limit search to specific domain")
    case_sensitive: bool = Field(default=False, description="Case-sensitive search")
    limit: int = Field(default=20, description="Maximum results to return", ge=1, le=100)
    search_mode: Literal["keyword", "semantic", "hybrid"] = Field(
        default="hybrid",
        description="Search mode: 'keyword' for lexical matching, 'semantic' for "
        "embedding-based similarity, 'hybrid' (default) combines both (70%% semantic + 30%% keyword)",
    )


class SchemaIndexInput(BaseModel):
    """Input model for schema_index tool."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    domain: str | None = Field(default=None, description="Get schemas for specific domain only")
    include_historical: bool = Field(default=False, description="Include historical section")


class SchemaCreateInput(BaseModel):
    """Input model for schema_create tool."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    schema_name: str = Field(
        ..., description="Name of the schema file (without .md extension)", min_length=1
    )
    content: str = Field(..., description="Markdown content for the schema file", min_length=1)
    domain: str | None = Field(default=None, description="Domain to add schema to in index")
    description: str | None = Field(
        default=None, description="Description to add to index table (1-2 sentences)"
    )
    add_to_index: bool = Field(default=True, description="Automatically add to SCHEMA_INDEX.md")

    @field_validator("schema_name")
    @classmethod
    def validate_schema_name(cls, v: str) -> str:
        """Validate schema name follows FEATURE_NAME_SCHEMA.md convention."""
        # Remove .md if present
        name = v.removesuffix(".md")
        # Check if it's uppercase with underscores
        if not name.isupper() or not all(c.isalnum() or c == "_" for c in name):
            raise ValueError(
                f"Schema name must follow FEATURE_NAME_SCHEMA.md convention (uppercase with underscores). Got: {v}"
            )
        if not name.endswith("_SCHEMA"):
            raise ValueError(f"Schema name must end with '_SCHEMA'. Got: {v}")
        return name


class SchemaUpdateInput(BaseModel):
    """Input model for schema_update tool."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    schema_name: str = Field(
        ..., description="Name of the schema file (with or without .md extension)", min_length=1
    )
    content: str = Field(
        ..., description="New markdown content to replace existing content", min_length=1
    )
    update_index_description: bool = Field(
        default=False, description="Update description in index if provided"
    )
    new_description: str | None = Field(default=None, description="New description for index")


class SchemaDeleteInput(BaseModel):
    """Input model for schema_delete tool."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    schema_name: str = Field(..., description="Name of the schema file to delete", min_length=1)
    remove_from_index: bool = Field(default=True, description="Remove from SCHEMA_INDEX.md")
    confirm: bool = Field(
        default=False, description="Confirmation flag to prevent accidental deletion (must be True)"
    )

    @field_validator("confirm")
    @classmethod
    def validate_confirm(cls, v: bool) -> bool:
        """Ensure confirm is True for deletion."""
        if not v:
            raise ValueError(
                "Deletion requires explicit confirmation. Set confirm=True to proceed."
            )
        return v


class SchemaDomainsInput(BaseModel):
    """Input model for schema_domains tool (no parameters)."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )


class KIGetInput(BaseModel):
    """Input model for ki_get tool — atomic KI entry lookup."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    key: str = Field(
        ...,
        description="Dot-notation key to look up (e.g., 'db.us.instance', 'gotcha.cloudflare.worker_to_worker_timeout')",
        min_length=1,
    )
    fuzzy: bool = Field(
        default=False,
        description="If True, return entries where key contains the query string",
    )


class KISetInput(BaseModel):
    """Input model for ki_set tool — atomic KI entry upsert."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    key: str = Field(
        ...,
        description="Dot-notation key (e.g., 'db.new_instance.name')",
        min_length=1,
    )
    value: str = Field(
        ...,
        description="The fact value",
        min_length=1,
    )
    source: str = Field(
        ...,
        description="Source proving this fact (e.g., 'src/api/server.py:L42' or 'GH#608')",
        min_length=1,
    )
    verified: str | None = Field(
        default=None,
        description="Verification date (YYYY-MM-DD). Defaults to today.",
    )
    extra_fields: dict | None = Field(
        default=None,
        description='Additional context fields (e.g., {"region": "us-central1", "note": "..."})',
    )
    section_hint: str | None = Field(
        default=None,
        description="Markdown section heading to append under if creating new entry (e.g., 'Database')",
    )


class KIListInput(BaseModel):
    """Input model for ki_list tool — list all KI keys."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    file_filter: str | None = Field(
        default=None,
        description="Only list keys from a specific KI file (e.g., 'KI_INFRA_SCHEMA')",
    )
    prefix_filter: str | None = Field(
        default=None,
        description="Only list keys matching this prefix (e.g., 'db.', 'gotcha.')",
    )


class KIMGetInput(BaseModel):
    """Input model for ki_mget tool — batch lookup of multiple keys."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    keys: list[str] = Field(
        ...,
        description="List of dot-notation keys to look up (e.g., ['db.us.instance', 'billing.system'])",
        min_length=1,
    )
    fuzzy: bool = Field(
        default=False,
        description="If True, match keys containing the query instead of exact match",
    )
