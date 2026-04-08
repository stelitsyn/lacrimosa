# Core Essentials

> **TDD is king. "Clean as you code" is queen.**
> **Match effort to complexity.** Use dispatch scoring below — don't default to agents for everything.

## Research Gate

For product/feature questions: check `spec/PRODUCT_SPEC.md` via KI first (`arch.spec.<domain>`).
For infrastructure, billing, architecture: search MCP schemas + Grep in parallel.
For code tasks where the relevant files are known: skip research, just read the code.
Full protocol: `core/essentials-reference.md`, `workflow/research-first.md`.

---

## Linear Integration (Auto-Loaded)

All non-trivial work (score ≥ 2) flows through Linear automatically. See `rules/linear-integration.md` for full protocol.
- **Kanban only** — no sprints/cycles
- Agents auto-create/update Linear issues via MCP tools
- `/next`, `/standup`, `/done` already integrated via `linear` CLI
- `/implement`, `/bugfix`, `/release`, `/pre-release` integrated via MCP

---

## Auto-Dispatch (PROACTIVE — No Permission Needed)

```
Score 5+ → DISPATCH IMMEDIATELY
Score 3-4 → Consider dispatch
Score 0-2 → Do directly
```

| Factor | Points |
|--------|--------|
| Each file to read | +1 |
| Each file to modify | +2 |
| Cross-domain (API + frontend) | +3 |
| Security implications | +2 |
| Exploratory search needed | +1 |
| Unknown codebase area | +1 |
| Multiple concerns | +1 per concern |

## Instant Triggers (Spawn Without Asking)

| User Says (or implies) | Immediately Spawn |
|------------------------|-------------------|
| Add endpoint/API/route | `backend-architect` |
| Add UI/component/page | `frontend-developer` |
| Find/explore/where is | Grep/Glob first. Only spawn Explore if >3 searches needed |
| Run tests/verify | `parallel-test-runner` |
| Fix bug/debug/error | `bugfix` skill → agents |
| Feature or multi-file change | `/implement` skill → phases 1-8 (load `workflow/phases-compact.md`) |
| Review code/PR | `pr-review-toolkit:review-pr` skill (multi-agent) + `code-reviewer` agent |
| Security audit/pre-release | `adversarial-verify` skill → 3-agent pattern |
| Security/auth/tokens | `security-officer` agent |
| Deploy/release | `devops-engineer` agent |
| Docs/explain | `knowledge-engineer` agent |
| Plan/design/architect | `Plan` agent |
| Create GH issue/ticket | If details known: create directly. If context needed: 1-2 Explore agents |

**Pre-Push Gate**: For changes touching 3+ files or any security-sensitive code, invoke `pr-review-toolkit:review-pr` before pushing. For trivial changes (typos, comments, single-file fixes), a self-review is sufficient.

**Post-Implementation Gate** (non-team workflows only — Agent Teams have their own QA via `20-manual-qa-instructions.md`):

```
TDD complete → Verify on staging → Create PR with proofs → Review loop → Merge
```

1. **Verify**: Deploy to staging (`./infra/deploy-staging.sh`)
   - UI/UX: browser via `mcp__claude-in-chrome__*` or Playwright — take screenshots
   - API/backend: curl/httpie against staging endpoints
   - Generate `REPORT_WITH_SCREENSHOTS.md` (see `workflow/staging-verification.md`)
2. **Create PR**: Include report + screenshots as evidence in PR body
3. **Review loop**: Invoke `pr-review-toolkit:review-pr` → fix all issues found → re-review. Repeat until zero issues.
4. **Merge**: Once review is clean, merge the PR

## Agent Teams (When to Escalate from Subagents)

> Load `workflow/agent-teams-summary.md` first, then `workflow/agent-teams-full.md` when spawning.

| Score 8+ | Use Agent Team |
|----------|----------------|
| Cross-domain (API + frontend + tests) | +4 |
| 3+ competing hypotheses to test | +3 |
| Teammates need to discuss/coordinate | +3 |
| 10+ files across 3+ subsystems | +3 |
| Long-running parallel investigation | +2 |

**Team triggers** — see `workflow/agent-teams-summary.md` for auto-sizing tiers and role list.

---

## Session Hygiene

**One session per contract.** Each task contract (GH issue / `/implement` invocation) runs in its own Claude session. Never mix unrelated contract work into one long session — context from previous contracts pollutes current work and causes drift.

---

## Solution Quality (HARD RULE)

> **NEVER propose "the simplest solution", workarounds, or shortcuts.**
> Deliver **complete, robust, production-grade solutions**.

| Forbidden | Required |
|-----------|----------|
| "The simplest approach would be..." | Full solution addressing all edge cases |
| "A quick workaround is..." | Proper fix at the root cause |
| "For now we can just..." | Permanent solution from the start |
| Skipping error handling "for simplicity" | Full error handling, validation, logging |
| Partial implementation with TODOs | Ship-ready code, no loose ends |

## Approach Discipline (Anti-Wrong-Approach)

> **Go direct. Don't cycle through approaches.** State your plan in 2-3 bullets before acting.

- If the first approach fails, diagnose WHY before trying another — don't shotgun
- If unsure which file/approach, ASK rather than guess-and-iterate
- Maximum 2 approach attempts before asking the user for guidance

---

## Project Standards

- **Testing**: pytest, TDD — cover meaningful paths and edge cases, not a test count target
- **Principles**: SOLID, DRY, no GOD-classes
- **Limits**: Max 300 lines/file, 30 lines/function
- **Documentation**: Context7 for library docs
- **Year**: 2026 for all doc references
- **Reports**: See `CLAUDE.md` Completion Reporting (single source of truth)

---

## Knowledge Index

See `core/knowledge-index.md` for full protocol.
Quick: `ki_get("key")` for single facts, `ki_list(prefix_filter="db.")` to browse, `ki_set(key, value, source)` to capture.

---

## Quick Reference

**GitHub CLI:**
```bash
gh issue list --search "X"    gh issue view <n>
gh issue create --title "..."  gh issue close <n>
```

**Testing** (scripts handle venv + .env + Docker — never activate venv manually for tests):
```bash
./run_all_tests.sh                # Full suite
./run_unit_tests.sh               # Unit only
./run_integration_tests.sh        # Integration only
./run_regression_tests.sh         # Regression only
./run_e2e_fast_tests.sh           # E2E fast
```

**Common Gotchas:**
1. Tests pass locally, fail CI → Check fixture isolation
2. Flaky tests → Timing dependencies
3. Import errors → Mock patch paths

**macOS Environment:**
- For tests: use `./run_*.sh` scripts (they handle venv, .env, Docker)
- For non-test python: use `.venv/bin/python` (never `source .venv/bin/activate`)
- Use `grep -E` not `grep -P` when Bash grep is needed (BSD grep has no Perl regex)
