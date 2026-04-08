# Self-Correction Prevention

> **Stop making the same mistakes. Check before acting. Match effort to complexity.**

## A. Hard-Coded Anti-Patterns (Enforced Unconditionally)

| Anti-Pattern | Prevention Rule |
|---|---|
| **Edit before Read** | NEVER call Edit/Write on a file you haven't Read in this conversation. Always Read first. |
| **Re-reading after failed edit** | If an Edit fails (old_string not found), re-Read the file, then retry with correct content — max 2 retries. |
| **Multiple edits to fix one change** | Plan the full change before the first Edit. Don't make partial edits and fix-up edits. |
| **Guessing file paths** | Use Glob/Grep to find files before editing. Don't guess paths and fail. |
| **Running same failing command twice** | If a Bash command fails, diagnose before retrying. Never retry identical command. |
| **Spawning agents for trivial lookups** | If a Grep or Glob can answer the question in 1 call, don't spawn an Explore agent. |
| **Writing tests after implementation** | In TDD mode, write tests BEFORE implementation. Don't retrofit tests. |
| **Editing generated/built files** | Never edit files in `node_modules/`, `.next/`, `__pycache__/`, `dist/`, `build/`. |
| **Blind test retry** | If tests fail, READ the error output, DIAGNOSE the cause, FIX the code, THEN rerun. Never rerun tests without a code change. Retrying a failing test without fixing anything is always a waste. |
| **Ignoring test output** | When tests fail, read the FULL error — traceback, assertion message, expected vs actual. Don't just see "FAILED" and retry or guess. |
| **Venv activation per command** | Never `source .venv/bin/activate && ...` — shell state doesn't persist. For tests: use `./run_*.sh` scripts. For non-test python: `.venv/bin/python`. |
| **Bash instead of dedicated tools** | Don't use `cat`/`head`/`tail` — use Read. Don't use `grep`/`rg` — use Grep. Don't use `find` — use Glob. Bash is for commands that have no dedicated tool equivalent. |
| **Committing with unstaged files** | ALWAYS `git add` all intended files BEFORE `git commit`. Never commit with unstaged tracked changes in the working tree — pre-commit stashes them, causing hooks to fail on reformatted files and requiring re-stage + re-commit. |
| **CWD drift after cd** | After `cd subdir && command`, CWD stays in subdir for ALL subsequent Bash calls. ALWAYS use absolute paths (`{project_root}/.venv/bin/python`) or `cd {project_root} &&` prefix. Never assume CWD is project root after any `cd`. |
| **Migration assumes fresh table** | NEVER use `if table not in tables: CREATE TABLE` for tables that might already exist from legacy migrations. Use `ADD COLUMN IF NOT EXISTS` for individual columns. Conditional CREATE TABLE silently skips all columns when the table pre-exists with fewer columns. |

## B. Self-Correction Detection & Learning

When you catch yourself making a mistake mid-conversation:

1. **Detect**: Notice when you're about to do something you just undid/redid
2. **Log**: After task completion, if you self-corrected 2+ times on the same pattern, invoke `/learn` with the pattern
3. **Prevent**: Before each action, mentally check against known anti-patterns above

## C. Proportionality Principle

> **Match effort to task complexity. Heavyweight processes are for heavyweight tasks.**

| Task Size | Appropriate Process |
|-----------|---------------------|
| Typo, single-line fix, comment | Direct edit. No agents, no reports, no staging. |
| Single-file bug fix | Read → test → fix → verify. Report only if runtime behavior changed. |
| Multi-file feature | Full workflow: agents, TDD, review, staging, report. |
| Cross-domain feature | Agent team with contracts, staging verification, full report. |

**When in doubt**: Start light, escalate if complexity reveals itself.
