# Learned Corrections (Structurally Enforced)

> These rules were learned from user corrections during past sessions.
> They are promoted here from `corrections.json` because rules files are ALWAYS loaded
> at session start — unlike corrections.json which requires manual loading.
> Source of truth: this file. corrections.json is the audit log.

## Tool Usage

- **Agent Teams vs Subagents**: When user says "spawn agentic team", "agent team", or "real team" — ALWAYS use `TeamCreate` + shared `TaskList` + `Agent` with `team_name` parameter. NEVER use background subagents (`Agent` with `run_in_background=true`) as substitute. Teams have peer communication; subagents don't.

- **Schema Search**: Use `mcp__schema-mcp__schema_search` (hybrid mode) for semantic schema discovery. Non-search operations use `schema_cli.py` via Bash.


## Git Safety

- **No git stash — ever**: Never use `git stash` for ANY reason — not for dirty trees, not for pre-push conflicts, not for "verifying pre-existing test failures", not for comparing before/after. It leads to lost work in multi-session development. Instead: for pre-existing test failures, fix root cause if safe, otherwise state they look unrelated and move on. For dirty trees: add generated/temp files to .gitignore, ensure clean tree before push. Hard-blocked at hook level (deny).

- **Git from project root**: Always run git commands from `{project_root}`, not subdirectories. Use absolute paths or `git -C <root>`.

## Testing & Debugging

- **Never check "already failing"**: If a test is broken, fix it immediately. Never use git stash or rollback to avoid fixing.

- **Agent team issues — fix first**: When agent team issues occur (idle, failing, not working), investigate and fix the root cause FIRST before proceeding with the original task.

## Workflow

- **Lacrimosa: Reality check before dispatch**: Before dispatching any worker, Lacrimosa MUST verify the actual state of the issue against Linear (live query), git (merged PRs, commits on main), and GitHub (open PRs). If work is already done but state.json or Linear is stale, reconcile both and add a Linear comment explaining why the status was corrected. Never trust state.json alone — it drifts when sessions crash.

- **Post-implementation gate is automatic**: After completing any implementation (even small fixes with passing tests), ALWAYS follow: deploy staging -> verify -> create PR -> review loop -> merge. Never stop at "tests pass" and ask.

- **Auto-capture bugs/ideas**: When user mentions a bug, idea, or feature — auto-create GH issue + Linear issue. Never let ideas go untracked.

- **Visual QA loop**: Any visual change (CSS, TSX, SVG, images, layouts, copy) requires autonomous visual QA: screenshot -> analyze -> fix -> re-verify in loop. See `rules/visual-qa-loop.md`.

- **Persist background agent IDs**: When dispatching long-running background agents, persist their IDs to state.json immediately so they survive context compaction. On resume, check state for in-flight agents.

- **Never skip Phase 4.1 Review Loop**: ALL implementations must go through the multi-reviewer feedback loop, regardless of how "straightforward" the change appears. Simplicity is not an excuse to bypass quality gates. The review loop exists to catch what you missed, not just for complex changes.

- **Lacrimosa: Learning events must be PROPERLY PROCESSED**: Never bulk-mark learning events as `processed=1` without reading and acting on each one. "Acknowledge and mark" is NOT processing. For each event: (1) read the full context, (2) analyze what happened, (3) take the appropriate action per event_type — create issue, post comment, adjust config, escalate, etc. as defined in the conductor spec, (4) THEN mark processed. Skipping steps 1-3 is unacceptable.

- **Lacrimosa: Workers must respect issue comments as stop signals**: Implementation workers MUST read ALL issue tracker comments before starting work. If any comment indicates the work is already done, not needed, a duplicate, or superseded — the worker must abort immediately and report `WORKER_FAILED reason=no_implementation_needed`. The pre-dispatch gate must also scan comments for stop signals before dispatching. Workers continuing to implement despite "not needed" comments is wasted compute and creates noise PRs.

## Serialization & State Safety

- **Never put non-serializable objects in checkpointed state**: When working with LangGraph (or any framework that persists state via serialization), NEVER inject runtime service objects (LLM clients, DB connections, HTTP clients, credential managers) into the graph state. These cause serialization failures at runtime. Instead, pass non-serializable services via the framework's config dict (not checkpointed) or via module-level singletons. **Pre-flight check**: before any change that adds data to graph state, verify every value is serializable (primitives, dicts, lists, strings, numbers, None).

- **Checkpointer changes require integration test with real serialization**: When modifying how the checkpointer connects or what enters the graph state, write a test that actually serializes the state (round-trip) before deploying. Unit tests with mocked checkpointers won't catch serialization failures.

## Verification

- **Fixes require retest — always**: Any code change made during prerelease, bugfix, or review (even trivial single-line fixes) MUST be retested before declaring the fix complete. Fixes are untested code. "I fixed it" without verification evidence is not a fix. Run relevant tests locally + verify on staging. Retest scope scales with fix scope: single-file cosmetic -> targeted retest; multi-file -> full regression.

- **Full positive AND negative test coverage**: When testing API endpoints or features (pre-release, QA, staging verification), ALWAYS test both positive (happy path) and negative (error) scenarios. Never test only error cases (auth blocked, invalid input) — verify the actual functionality works end-to-end with real data. For endpoints: test with valid auth + valid input -> expected success response, THEN test error paths. For approve/reject flows: create real pending records, approve one, reject another, verify state transitions.

## Communication

- **Show task list when idling**: When acting as PM/team-lead and waiting for teammates, always call `TaskList` and display the output so the user can see current statuses, ownership, and blockers. Never just say "waiting" — show the data.

- **PM must never go idle during team work**: Always create a PM coordination task (e.g., "Coordinate team: monitor progress") and keep it `in_progress` for the team's lifetime. This prevents the UI from showing "Idle - teammates running" with no task list visible. Update the `activeForm` with current progress (e.g., "Coordinating team (3/6 tasks remaining)").

## Environment

- **Python venv**: Use `.venv/bin/python` directly (never `source .venv/bin/activate` — shell state doesn't persist between Bash calls). For tests: use `./run_*.sh` scripts.

- **Docker fallback**: Check local socket first; if unavailable, use remote Docker host at `DOCKER_HOST=tcp://{remote_docker_host}:2375`.

- **Browser screenshots**: Use `mcp__chrome-devtools__take_screenshot(pageId, filePath=..., fullPage=true)` for all browser QA. Always capture full-page (not just viewport). After capturing, read the screenshot back and thoroughly analyze the entire page content — verify every expected element, check for visual anomalies, layout issues, and state coherence. Never use screencapture, osascript, or CGWindowID.
