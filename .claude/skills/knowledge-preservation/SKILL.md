---
name: knowledge-preservation
description: Post-implementation knowledge capture including schema updates, KI artifact updates, and documentation changes. Use at the end of any implementation or bugfix workflow to preserve learnings, gotchas, and architectural decisions.
---

# Knowledge Preservation

Systematic capture of learnings after implementation or bugfix completion.

## When to Update

Trigger knowledge preservation when:

- Bug fix reveals a gotcha or non-obvious behavior
- Implementation establishes a new pattern
- State machines, data flows, or API contracts change
- Configuration or behavior changes affect users
- Credit costs or billing rules change
- New UI flows, error handling patterns, or API response codes added
- Security controls or safety rules added

## Step 1: Identify Affected Domains

Review the git diff to understand what changed. Map changes to schema domains:

| Changed Area | Schema Domain Keywords |
|-------------|----------------------|
| Feature A/orchestrator/planning | feature orchestrator, query planning |
| Messaging/outbound/nurturing | messaging outbound, nurturing, resolver |
| Billing/credits/costs | billing, credits, subscription, pricing |
| Coordination/goals/workflow | coordination, workflow, goal, step execution |
| Frontend/portal/UI | web portal, subscription, outbox, settings |
| Realtime/WebSocket/streaming | realtime flow, websocket, streaming |
| Auth/security/tokens | auth, security, OWASP |
| Database/migrations | database, schema, migration |
| Infrastructure/deploy | multiregion, cloudflare, deploy |

## Step 2: Schema Updates (via MCP schema tools)

**MANDATORY** when code changes touch state machines, data flows, API contracts, credit costs, new features, or behavioral changes.

### Load MCP schema tools (deferred — must load first)

```
ToolSearch("select:mcp__schema-mcp__schema_search")
ToolSearch("select:mcp__schema-mcp__schema_read")
ToolSearch("select:mcp__schema-mcp__schema_update")
```

### Search for affected schemas

```
mcp__schema-mcp__schema_search(params={"query": "<domain keywords>"})
```

Search for EACH affected domain identified in Step 1. Multiple searches in parallel.

### Read the most relevant schemas

```
mcp__schema-mcp__schema_read(params={"schema_name": "FOUND_SCHEMA_NAME"})
```

### Update each affected schema

```
mcp__schema-mcp__schema_update(params={
    "schema_name": "SCHEMA_NAME",
    "content": "<full updated content>"
})
```

**Update rules:**
- **Preserve ALL existing content** — only ADD new sections or MODIFY changed sections
- Update `**Updated**:` date to today
- Add new GH issue numbers to `**Issues**:` header
- Add new sections for new behaviors
- Update existing sections where behavior changed
- Add new safety rules if security controls were added
- Update credit costs if billing changed
- Update API response descriptions if new error codes added
- Update component hierarchy if new UI elements added

### Common schema update patterns

| Code Change | Schema Update |
|------------|---------------|
| New feature fallback behavior | FEATURE_A_ENGINE_SCHEMA — add fallback section |
| Credit cost change | BILLING_SCHEMA — update cost table |
| New API error code | WORKFLOW_SCHEMA — update endpoint docs |
| New UI component/flow | PORTAL_SUBSCRIPTION_SCHEMA — add component section |
| New messaging behavior | MESSAGING_SCHEMA — update flow docs |
| New realtime state | REALTIME_FLOW_SCHEMA — update state diagram |
| Auth/security change | AUTH_SCHEMA — update auth flow |
| Database model change | DB_MIGRATION_SCHEMA — update model docs |

## Step 3: SCHEMA_INDEX Update

If a NEW schema was created (not just updated), update `schemas/SCHEMA_INDEX.md`:

```
mcp__schema-mcp__schema_search(params={"query": "SCHEMA_INDEX"})
```

## Step 4: MEMORY.md Update

Update project memory when:
- New gotcha or pattern discovered (e.g., Cloudflare worker timeout)
- New architectural decision made
- New project convention established
- Deployment/infrastructure lesson learned

```
Edit(file_path="{memory_dir}/MEMORY.md", ...)
```

## Step 5: KI Updates (Atomic Facts)

Capture new facts atomically using `ki_set` — no need to rewrite entire schemas:

```
# Load KI tools first
ToolSearch("select:mcp__schema-mcp__ki_get,mcp__schema-mcp__ki_set")

# Check if fact already exists
ki_get(key="gotcha.new_finding")

# Upsert the fact
ki_set(key="gotcha.new_finding", value="description of gotcha", source="file.py:L42")
```

**What to capture as KI entries:**
- **Gotchas/pitfalls:** `gotcha.*` — why did the bug occur? How to avoid it?
- **New infrastructure:** `db.*`, `cloudrun.*`, `url.*` — new endpoints, services, instances
- **Business rules:** `billing.*`, `credits.*` — pricing changes, cost rules
- **Code locations:** `code.*` — new key handlers, services, entry points
- **Decisions:** `decision.*` — architectural choices with rationale
- **API changes:** `api.*` — new endpoints, changed routes
- **DB changes:** `db.table.*` — new tables, columns, relationships

## Step 6: Documentation Updates

If fix changes user-facing behavior, configuration, or API:

- Update README if applicable
- Update inline docstrings
- Update CHANGELOG for release notes

## Step 7: GH Issue Closure

Close GitHub issue with comprehensive summary:

```bash
gh issue close <n> --comment "$(cat <<'EOF'
## Summary
Root Cause: ...
Fix: ...
Tests: ...

## Schemas Updated
- SCHEMA_1 — added X section
- SCHEMA_2 — updated Y

## Files Changed
- file1.py — description
- file2.tsx — description

## Verified
All tests pass.
EOF
)"
```

## Final Checklist

- [ ] Identified all affected domains from git diff
- [ ] Searched MCP schemas for ALL affected domains (not just one)
- [ ] Read and updated ALL affected schemas
- [ ] Updated dates and issue references in schema headers
- [ ] SCHEMA_INDEX updated if new schema created
- [ ] MEMORY.md updated if new pattern/gotcha discovered
- [ ] KI updated with root cause and prevention notes
- [ ] Docs updated if user-facing behavior changed
- [ ] GH issue closed with summary listing schemas updated
