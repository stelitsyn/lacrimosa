# Deploying Lacrimosa Memory

Claude Code's memory system stores operational learnings in per-project directories at
`~/.claude/projects/<encoded-project-path>/memory/`. These memories are automatically
loaded at session start and help Claude avoid repeating past mistakes.

This directory contains pre-built memories from production Lacrimosa operation — hard-won
lessons about conductor architecture, specialist management, QA patterns, and ceremony
execution.

## Quick Deploy

```bash
# From the Lacrimosa repo root:
./memory/deploy.sh
```

The script:
1. Detects your project path encoding (how Claude Code encodes your repo's absolute path)
2. Creates the memory directory at `~/.claude/projects/<encoded-path>/memory/`
3. Copies all `.md` files except `DEPLOY.md`; `deploy.sh` is excluded by the `.md` glob

## Manual Deploy

If the script doesn't work for your setup:

```bash
# 1. Find your project's encoded path
#    Claude Code replaces all `/` with `-` in the absolute path.
#    Example: /home/user/projects/lacrimosa -> -home-user-projects-lacrimosa
REPO_PATH=$(pwd)
ENCODED=$(echo "$REPO_PATH" | sed 's|/|-|g')

# 2. Create memory directory
mkdir -p "$HOME/.claude/projects/${ENCODED}/memory"

# 3. Copy memory files (not deploy artifacts)
for f in memory/*.md; do
  base=$(basename "$f")
  [[ "$base" == "DEPLOY.md" ]] && continue
  cp "$f" "$HOME/.claude/projects/${ENCODED}/memory/"
done
```

## What Gets Deployed

| File | Category | What It Teaches |
|------|----------|-----------------|
| `MEMORY.md` | Index | Master index of all memories (auto-loaded by Claude) |
| `feedback_lacrimosa_v3_architecture.md` | Architecture | tmux conductor, Agent Teams dispatch, verification gates |
| `feedback_commit_engine_changes.md` | Operations | Engine fixes must land on main immediately |
| `feedback_lacrimosa_self_improvement.md` | Operations | Self-detect and self-fix without human supervision |
| `feedback_lacrimosa_never_idle.md` | Operations | 4-signal idle detection (don't re-trigger working specialists) |
| `feedback_specialist_restart_logic.md` | Operations | Multi-signal check before restarting specialists |
| `feedback_worktree_isolation_mandatory.md` | Git Safety | All agents must use isolation="worktree" |
| `feedback_ceremony_auto_actions.md` | Ceremonies | Ceremonies must execute actions, not just analyze |
| `feedback_daily_cap_counting.md` | Trust Tiers | Sub-issues count as one toward daily cap |
| `feedback_agent_teams_vs_subagents.md` | Teams | TeamCreate for real teams, not background subagents |
| `feedback_staging_verification_mandatory.md` | QA | Staging deploy + browser verify after all implementations |
| `feedback_visual_qa_loop.md` | QA | Screenshot-analyze-fix-reverify loop for visual changes |
| `feedback_visual_qa_release_gate.md` | QA | Visual anomalies block releases |
| `feedback_qa_agent_screenshot_validation.md` | QA | Agents must verify page content, not blindly screenshot |
| `feedback_browser_qa_tools.md` | QA | chrome-devtools MCP for all browser QA |
| `feedback_fix_retest_mandatory.md` | QA | All fixes require retesting |
| `feedback_test_plan_specificity.md` | QA | Test plans must cover specific changes, not just generic regression |

## Adding Your Own Memories

As you operate Lacrimosa, Claude Code will accumulate its own memories. You can also
manually create memories following this format:

```markdown
---
name: short-descriptive-name
description: One-line description used to decide relevance in future sessions
type: feedback
---

The rule or learning.

**Why:** What went wrong / what prompted this learning.

**How to apply:** Specific guidance for when/how to use this knowledge.
```

Memory types:
- `feedback` — corrections and confirmed approaches (most memories are this type)
- `project` — ongoing project state, decisions, constraints
- `user` — user preferences and working style
- `reference` — pointers to external resources

## Customizing for Your Product

These memories reference generic concepts (staging, issue tracker, ceremonies). If your
setup differs:

1. **Issue tracker**: Memories reference "issue tracker" generically. Replace with your
   specific tool (Linear, Jira, GitHub Issues) in the relevant memory files.

2. **Staging deploy**: `feedback_staging_verification_mandatory.md` says "deploy to staging."
   Update the deploy command to match your infrastructure.

3. **Browser QA tools**: `feedback_browser_qa_tools.md` assumes chrome-devtools MCP. If you
   use a different browser automation setup, adjust accordingly.

4. **Trust tiers / daily caps**: `feedback_daily_cap_counting.md` references trust tier caps.
   Adjust the numbers to match your `config.yaml` settings (copied from `config.example.yaml` during setup).
