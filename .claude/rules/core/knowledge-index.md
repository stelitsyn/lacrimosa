# Knowledge Index (KI) — Unified Source of Truth

> KI entries live in `schemas/KI_*_SCHEMA.md` files. Dense KV format, source-linked.
> CLI: `.venv/bin/python schema_cli.py ki get "key"` for single lookups, `ki set "key" "value" "source"` for upserts.
> Semantic search stays in MCP: `mcp__schema-mcp__schema_search`.

## READ Convention — Route by Query Type

| Query Type | Action |
|------------|--------|
| **Code** (functions, classes, logic, file contents) | Grep/Glob directly — KI doesn't store code |
| **Infrastructure** (DB, URLs, secrets, services, GCP) | `schema_cli.py ki get` first — faster than grepping config |
| **Business rules** (billing, plans, credits, conventions) | `schema_cli.py ki get` first |
| **Architecture** (service flows, relationships) | `schema_cli.py ki get` first, then code if more detail needed |
| **Mixed/unsure** | `schema_cli.py ki get` + Grep in parallel (single message) |

**KI tools (CLI via Bash):**
- `.venv/bin/python schema_cli.py ki get "key"` — single lookup
- `.venv/bin/python schema_cli.py ki mget key1 key2` — batch lookup
- `.venv/bin/python schema_cli.py ki list --prefix "db."` — browse by prefix
- `.venv/bin/python schema_cli.py ki set "key" "value" "source"` — upsert

**Schema tools (CLI via Bash):**
- `.venv/bin/python schema_cli.py schema read NAME` — read schema
- `.venv/bin/python schema_cli.py schema list` — list schemas
- `.venv/bin/python schema_cli.py schema index` — get index by domain
- `.venv/bin/python schema_cli.py schema domains` — list domains
- `.venv/bin/python schema_cli.py schema create NAME --content "..." --domain "..."` — create
- `.venv/bin/python schema_cli.py schema update NAME --content "..."` — update
- `.venv/bin/python schema_cli.py schema delete NAME --confirm` — delete

**Semantic search (MCP — needs warm embedding model):**
- `mcp__schema-mcp__schema_search` — semantic/hybrid search across schemas
- `mcp__schema-mcp__schema_resolve` — combined search + read

If KI misses → explore normally, then capture the fact (see WRITE below).

**KI domains and key prefixes:**

| Prefix | File | Contains |
|--------|------|----------|
| `db.*`, `cloudrun.*`, `url.*`, `gcp.*`, `firebase.*`, `secrets.*`, `dev.*` | KI_INFRA | DB instances, services, URLs, secrets |
| `arch.*` | KI_ARCHITECTURE | System flows, service relationships |
| `code.*` | KI_CODE_MAP | Key handlers, services, entry points |
| `api.*` | KI_API_SURFACE | Endpoints, methods, ownership |
| `db.table.*` | KI_DB_MAP | Tables, columns, relationships |
| `gotcha.*` | KI_GOTCHAS | Pitfalls, solved issues |
| `billing.*`, `plan.*`, `credits.*`, `payments.*` | KI_BUSINESS_RULES | Pricing, credits, billing |
| `convention.*` | KI_CONVENTIONS | Coding rules, deployment, workflow |
| `decision.*` | KI_DECISIONS | Architectural decisions + rationale |
| `hierarchy.*` | KI_SERVICE_HIERARCHY | Service class hierarchy |

## WRITE Convention — Capture on Discovery

When a work session discovers new infrastructure, business, or architecture facts, capture them:

```bash
.venv/bin/python schema_cli.py ki set "gotcha.new_finding" "description" "file.py:L42"
```

**Capture when you discover:**
- New infrastructure facts (endpoints, services, secrets, URLs)
- New code entry points or service boundaries
- New business rules or pricing changes
- Gotchas, pitfalls, or solved debugging insights
- Architectural decisions with rationale
- New DB tables, columns, or relationships

**Write-through validation:**
- Source file must exist and support the claimed value
- If source is dead → do NOT write. Flag as needing source.
- Every entry MUST have: key, value, source, verified date

## When NOT to Write KI
- Temporary/session-specific state
- Unverified hypotheses
- Implementation details that change frequently (use detail schemas for those)
