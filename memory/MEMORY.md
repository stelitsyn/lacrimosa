# Lacrimosa Project Memory

> Operational learnings from running Lacrimosa in production.
> These memories help Claude Code avoid repeating mistakes across sessions.
> Deploy to `~/.claude/projects/<your-project-path>/memory/` — see `DEPLOY.md`.

## Lacrimosa Architecture & Operations

- [v3 Architecture Decisions](feedback_lacrimosa_v3_architecture.md) — tmux conductor, Agent Teams dispatch, verification, context hygiene
- [Commit Engine Changes Immediately](feedback_commit_engine_changes.md) — engine fixes must land on main within the same cycle
- [Self-Improvement Autonomy](feedback_lacrimosa_self_improvement.md) — conductor must self-detect and self-fix operational issues
- [Never Idle When Work Exists](feedback_lacrimosa_never_idle.md) — 4-signal check before deciding a specialist is truly idle
- [Specialist Restart Logic](feedback_specialist_restart_logic.md) — multi-signal verification before restarting specialists
- [Worktree Isolation Mandatory](feedback_worktree_isolation_mandatory.md) — all dispatched agents must use isolation="worktree"
- [Sprint Focus Distillation](feedback_sprint_focus_distillation.md) — turn active sprint/project memories into routing context without publishing private roadmaps
- [Ceremony Auto-Execution](feedback_ceremony_auto_actions.md) — ceremonies must DO work, not just analyze and report
- [Daily Cap Counts Parent Issues](feedback_daily_cap_counting.md) — sub-issues of decomposed parent = 1 toward daily cap
- [Learning Events Must Be Properly Processed](feedback_learning_events_processing.md) — never bulk-mark as processed without acting on each
- [Workers Must Respect Stop Signals](feedback_worker_stop_signals.md) — read issue comments before starting, abort if work is unnecessary
- [Codex Backend Adapter](feedback_codex_backend_adapter.md) — isolate backend CLI differences behind a runner and sanitize memory before public release

## Agent Teams & Dispatch

- [Agent Teams vs Subagents](feedback_agent_teams_vs_subagents.md) — TeamCreate for real teams, never background subagents
- [Staging Verification Mandatory](feedback_staging_verification_mandatory.md) — deploy + browser verify after ALL implementations

## Quality Assurance & Verification

- [Visual QA Feedback Loop](feedback_visual_qa_loop.md) — autonomous screenshot-analyze-fix-reverify loop
- [Visual Anomalies are Release Blockers](feedback_visual_qa_release_gate.md) — visual bugs block releases same as functional bugs
- [QA Agent Screenshot Validation](feedback_qa_agent_screenshot_validation.md) — agents must verify content, not blindly screenshot
- [Browser QA via chrome-devtools](feedback_browser_qa_tools.md) — chrome-devtools MCP for all browser verification
- [Fix-Retest Mandatory](feedback_fix_retest_mandatory.md) — all code fixes require retesting
- [Fix Findings Regardless of Origin](feedback_fix_findings_regardless_of_origin.md) — unrelated/pre-existing findings must be fixed, tracked, or escalated
- [Use Strong Models for High-Context Review](feedback_high_context_model_selection.md) — legal, policy, security, and compliance work should not be downshifted when precision matters
- [Test Plan Specificity](feedback_test_plan_specificity.md) — test plans must cover specific features/bugs, not just generic regression
