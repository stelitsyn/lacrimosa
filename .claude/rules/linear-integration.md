# Linear Integration — Zero-Touch Automation

> **All work flows through Linear. No manual updates. Agents handle everything.**
> **Kanban only — no sprints/cycles.** Issues flow: Backlog -> Todo -> In Progress -> In Review -> Done.

## When to Create a Linear Issue

| Trigger | Action |
|---------|--------|
| `/implement` invoked | Find or create Linear issue |
| `/bugfix` invoked | Find or create Linear issue |
| User mentions bug/idea | Auto-create issue (existing rule) |
| Agent team spawned | Create parent issue + sub-issues |
| Epic detected | Create parent + child issues in Linear |

**Skip Linear for:** typos, single-line config fixes, docs-only changes (score 0-1).

## Auto-Create Convention

When starting work without an existing Linear issue:

```
1. Search: mcp__linear-server__list_issues(query="<keywords>", team="{linear_team}")
2. If match found -> use it
3. If not -> create:
   mcp__linear-server__save_issue(
     title="<concise title>",
     team="{linear_team}",
     project="<matching project>",
     labels=["<Area label>", "<Domain label>"],
     priority=<from dispatch score>,
     assignee="me",
     state="In Progress",
     description="<context from GH issue or user request>"
   )
4. Capture LINEAR_ISSUE_ID for status updates
```

## Project Routing

Configure project routing in `config.yaml` under `project_routing`. Map keywords to Linear projects.

## Label Assignment

Apply labels from two groups minimum:

**Area** (what feature): Configure per product
**Domain** (what layer): Frontend, Backend, API, DevOps, Security, Mobile, Database

Optional:
**Type**: Tech Debt, Performance, SEO, Documentation, Content

## Priority Mapping

| Dispatch Score | Linear Priority |
|----------------|-----------------|
| 8+ (Agent Team) | 1 (Urgent) |
| 5-7 (Must dispatch) | 2 (High) |
| 3-4 (Consider dispatch) | 3 (Normal) |
| 0-2 (Direct) | 4 (Low) |

## SLA Policies

Linear SLA policies enforce response and resolution time targets.

| Priority | First Response | Resolution | Breach Action |
|----------|---------------|------------|---------------|
| Urgent (1) | 4 hours | 24 hours | Email notification |
| High (2) | 8 hours | 3 days | Email notification |
| Normal (3) | 24 hours | 1 week | None |
| Low (4) | No SLA | No SLA | None |

Configure in: Linear -> Settings -> Team -> SLA

When creating issues with priority 1-2, SLA timers start automatically.

## Status Updates During Workflows

Agents update Linear issue status at phase transitions. Use MCP tools directly:

### /implement phases -> Linear status

| Phase | Linear Action |
|-------|---------------|
| Phase 1+2 start | `save_issue(status="In Progress", assignee="me")` |
| Phase 3 (TDD) | `save_comment("Tests written. X test cases covering: ...")` |
| Phase 4 complete | `save_comment("Implementation complete. Files: ...")` |
| Phase 4.1 (Review) | `save_issue(status="In Review")` |
| Phase 5 (Tests pass) | `save_comment("All tests passing: X unit, Y integration, Z regression")` |
| Phase 8 (Done) | `save_issue(status="Done")` + `save_comment("Completed. PR: #XX")` |
| Tests fail / blocked | `save_comment("Blocked: <reason>")` — keep In Progress |

### /bugfix phases -> Linear status

| Phase | Linear Action |
|-------|---------------|
| Phase 1 (Analysis) | `save_issue(status="In Progress", assignee="me")` |
| Phase 2 (Hypotheses) | `save_comment("Hypotheses: H1: ..., H2: ..., H3: ...")` |
| Phase 4 (Fix) | `save_comment("Root cause confirmed: <H#>. Fix applied to N files.")` |
| Phase 5 (Verify) | `save_issue(status="In Review")` |
| Phase 6 (Finalize) | `save_issue(status="Done")` + `save_comment("Fixed. PR: #XX. Regression tests: N")` |

### /release -> Linear milestones

| Step | Linear Action |
|------|---------------|
| Release tagged | Update milestone progress for related project |
| Issues in release | Close all Linear issues included in the release |
| Post-release | `save_comment` on milestone with version + release notes link |

## Comment Format

Keep comments structured and scannable:

```markdown
**Phase N complete** — [phase name]
- Summary: <what was done>
- Files: <key files touched>
- Tests: <pass/fail counts>
- Next: <what happens next>
```

## Branch Naming

When creating branches from Linear issues:
```
{issue_prefix_lower}-{issue-number}-{short-description}
# Example: prj-42-add-webhook-integration
```

## GitHub <-> Linear Linking

- **PR title**: Include `{ISSUE_PREFIX}-XX` identifier
- **PR body**: Include Linear issue URL
- **Commit messages**: Reference `{ISSUE_PREFIX}-XX` when relevant
- **GH issue body**: Link to Linear issue URL if both exist

## GitHub Integration (Native)

Linear's native GitHub integration handles PR lifecycle automation:

| Event | Linear Action |
|-------|---------------|
| PR opened with issue prefix in branch | Issue -> In Progress |
| PR merged | Issue -> Done |
| PR closed without merge | No change |
| Commit references issue prefix | Linked to issue |

**Setup:** Linear -> Settings -> Integrations -> GitHub -> Connect repo

This reduces the need for Claude Code to manually update status on PR events — Linear handles it natively.

## Epic Handling

When `/implement` detects an epic (Phase 0):
1. Create parent Linear issue with sub-issues (using `parentId`)
2. Each sub-issue gets its own labels, project, assignee
3. Sub-issues use `blockedBy` for dependency ordering
4. Parent issue tracks overall progress via comments
5. Close parent when all children are Done

## What NOT to Track in Linear

- One-off git operations (stash, rebase, merge)
- CLAUDE.md / rules file updates (internal tooling)
- Memory file updates
- KI schema updates (these are knowledge, not tasks)
