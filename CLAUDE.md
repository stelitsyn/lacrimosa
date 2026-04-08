# Adapted from a production CLAUDE.md — customize the placeholders, keep the rules

> **TDD is king. "Clean as you code" is queen.**

## Core Philosophy

Match effort to task complexity. Use agents and skills when they add value, not by default.
Deliver complete, robust, production-grade solutions. Never propose "the simplest solution."

---

## Auto-Dispatch Scoring

```
Score 5+ → DISPATCH IMMEDIATELY (spawn agents without asking)
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

### Instant Triggers (Spawn Without Asking)

| User Says (or implies) | Immediately Spawn |
|------------------------|-------------------|
| Add endpoint/API/route | `backend-architect` |
| Add UI/component/page | `frontend-developer` |
| Find/explore/where is | Grep/Glob first. Only spawn Explore if >3 searches needed |
| Run tests/verify | `parallel-test-runner` |
| Fix bug/debug/error | `bugfix` skill -> agents |
| Feature or multi-file change | `/implement` skill -> phases 1-8 |
| Review code/PR | `code-reviewer` agent |
| Security/auth/tokens | `security-officer` agent |
| Deploy/release | `devops-engineer` agent |
| Docs/explain | `knowledge-engineer` agent |
| Plan/design/architect | `Plan` agent |

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

---

## Approach Discipline (Anti-Wrong-Approach)

> **Go direct. Don't cycle through approaches.** State your plan in 2-3 bullets before acting.

- If the first approach fails, diagnose WHY before trying another -- don't shotgun
- If unsure which file/approach, ASK rather than guess-and-iterate
- Maximum 2 approach attempts before asking the user for guidance

---

## Anti-Patterns (Enforced Unconditionally)

| Anti-Pattern | Prevention Rule |
|---|---|
| **Edit before Read** | NEVER call Edit/Write on a file you haven't Read in this conversation. Always Read first. |
| **Re-reading after failed edit** | If an Edit fails (old_string not found), re-Read the file, then retry with correct content -- max 2 retries. |
| **Multiple edits to fix one change** | Plan the full change before the first Edit. Don't make partial edits and fix-up edits. |
| **Guessing file paths** | Use Glob/Grep to find files before editing. Don't guess paths and fail. |
| **Running same failing command twice** | If a Bash command fails, diagnose before retrying. Never retry identical command. |
| **Spawning agents for trivial lookups** | If a Grep or Glob can answer the question in 1 call, don't spawn an Explore agent. |
| **Writing tests after implementation** | In TDD mode, write tests BEFORE implementation. Don't retrofit tests. |
| **Editing generated/built files** | Never edit files in `node_modules/`, `.next/`, `__pycache__/`, `dist/`, `build/`. |
| **Blind test retry** | If tests fail, READ the error output, DIAGNOSE the cause, FIX the code, THEN rerun. Never rerun tests without a code change. Retrying a failing test without fixing anything is always a waste. |
| **Ignoring test output** | When tests fail, read the FULL error -- traceback, assertion message, expected vs actual. Don't just see "FAILED" and retry or guess. |
| **Venv activation per command** | Never `source .venv/bin/activate && ...` -- shell state doesn't persist. For tests: use `./run_*.sh` scripts. For non-test python: `.venv/bin/python`. |
| **Bash instead of dedicated tools** | Don't use `cat`/`head`/`tail` -- use Read. Don't use `grep`/`rg` -- use Grep. Don't use `find` -- use Glob. Bash is for commands that have no dedicated tool equivalent. |
| **Committing with unstaged files** | ALWAYS `git add` all intended files BEFORE `git commit`. Never commit with unstaged tracked changes in the working tree -- pre-commit stashes them, causing hooks to fail on reformatted files and requiring re-stage + re-commit. |
| **CWD drift after cd** | After `cd subdir && command`, CWD stays in subdir for ALL subsequent Bash calls. ALWAYS use absolute paths or `cd /project/root &&` prefix. Never assume CWD is project root after any `cd`. |
| **Migration assumes fresh table** | NEVER use `if table not in tables: CREATE TABLE` for tables that might already exist from legacy migrations. Use `ADD COLUMN IF NOT EXISTS` for individual columns. |

---

## Self-Correction Detection & Learning

When you catch yourself making a mistake mid-conversation:

1. **Detect**: Notice when you're about to do something you just undid/redid
2. **Log**: After task completion, if you self-corrected 2+ times on the same pattern, invoke `/learn` with the pattern
3. **Prevent**: Before each action, mentally check against the anti-patterns table above

---

## Proportionality Principle

> **Match effort to task complexity. Heavyweight processes are for heavyweight tasks.**

| Task Size | Appropriate Process |
|-----------|---------------------|
| Typo, single-line fix, comment | Direct edit. No agents, no reports, no staging. |
| Single-file bug fix | Read -> test -> fix -> verify. Report only if runtime behavior changed. |
| Multi-file feature | Full workflow: agents, TDD, review, staging, report. |
| Cross-domain feature | Agent team with contracts, staging verification, full report. |

**When in doubt**: Start light, escalate if complexity reveals itself.

---

## Project Standards

- **Testing**: pytest, TDD -- cover meaningful paths and edge cases, not a test count target
- **Principles**: SOLID, DRY, no GOD-classes
- **Limits**: Max 300 lines/file, 30 lines/function
- **Python**: Use `.venv/bin/python` directly (never `source .venv/bin/activate`)

---

## Testing

Scripts handle venv + .env + Docker -- never activate venv manually for tests:

```bash
./run_all_tests.sh                # Full suite
./run_unit_tests.sh               # Unit only
./run_integration_tests.sh        # Integration only
./run_regression_tests.sh         # Regression only
./run_e2e_fast_tests.sh           # E2E fast
```

### Common Gotchas

1. Tests pass locally, fail CI -> Check fixture isolation
2. Flaky tests -> Timing dependencies
3. Import errors -> Mock patch paths

---

## Git Operations

- When committing, handle stale `index.lock` files and pre-commit hook failures gracefully -- remove lock files and retry automatically rather than failing.
- When creating GitHub releases or tags, always ensure `git push` completes BEFORE running `gh release create` to avoid tag misalignment on wrong commits.
- Release notes must not include marketing language, business-sensitive details, or customer-specific information. Keep them technical and factual.

---

## General Workflow

When fixing issues, address the root cause directly rather than attempting multiple workarounds. If the first approach fails, step back and reconsider the underlying problem before trying another workaround.

### Post-Implementation Gate

```
TDD complete -> Verify on staging -> Create PR with proofs -> Review loop -> Merge
```

1. **Verify**: Deploy to staging, test UI/UX and API endpoints
2. **Create PR**: Include report + screenshots as evidence in PR body
3. **Review loop**: Invoke code review -> fix all issues found -> re-review. Repeat until zero issues.
4. **Merge**: Once review is clean, merge the PR

---

## Session Hygiene

**One session per contract.** Each task contract (GH issue / `/implement` invocation) runs in its own Claude session. Never mix unrelated contract work into one long session -- context from previous contracts pollutes current work and causes drift.

---

## Linear Integration

All non-trivial work (dispatch score >= 2) flows through Linear automatically:
- **Kanban only** -- no sprints/cycles
- Agents auto-create/update Linear issues via MCP tools
- Status updates at each workflow phase transition

---

## Development Setup

- Virtual environment: `.venv`
- Requirements: `requirements.txt`, `requirements.prod.txt`
- Use pinned versions for all dependencies

---

## Security

Scan for vulnerabilities before major deployments or dependency updates:
- Frontend: `npm audit`
- Backend: `pip-audit` or `safety check`, `bandit -r {source_dir}/`
- Action required by severity: CRITICAL/HIGH -> block deployment; MEDIUM -> fix within sprint; LOW -> track

---

## Deployment

Customize these for your infrastructure:

```bash
# Staging: always build fresh before deploying
./{infra}/deploy-staging-fresh.sh

# Production: ensure git push completes before tagging releases
git push origin main && gh release create v{version} --generate-notes
```

### Migration Order (generalized)

1. Staging environments first (no backup needed)
2. **Create database backups BEFORE production migrations**
3. Production environments

### Dependency Management

When adding a new dependency:
1. Add to **all** requirements files
2. Use **pinned versions** (e.g., `package==1.2.3`)
3. Verify compatibility across all deployment targets
