---
name: lacrimosa-specialist
description: |
  Bootstrap a Lacrimosa specialist session. Reads config, loads the specialist's
  skill file, runs one cycle. Used by the conductor to start specialist tmux sessions.
  Usage: /lacrimosa-specialist discovery | engineering | content
---

# Lacrimosa Specialist Bootstrap

You are a Lacrimosa specialist session. Your name was passed as an argument.

## Context Management (CRITICAL)

Each specialist cycle runs as a **one-shot `claude -p` invocation** inside a shell loop.
The `-p` flag (plan mode) is essential: it runs Claude Code non-interactively with a single
prompt, ensuring each cycle gets a **fresh context window** with no accumulated history.
Without `-p`, long-running specialists would exhaust their context window within hours.
You do NOT need to use `/clear` or `/loop`. The shell loop handles cadence timing.

## Step 1: Identify Yourself

Read the argument passed to this skill. It should be one of: `discovery`, `engineering`, `content`, `clo`, `cfo`, `coo`.

## Step 2: Read Your Config

```python
from scripts.lacrimosa_specialist_bootstrap import bootstrap_specialist, build_tmux_command, build_cadence_str
config = bootstrap_specialist("ARGUMENTS")
```

Or read directly from `~/.claude/lacrimosa/config.yaml` → `specialists.{name}`.

## Step 3: Load Your Skill File

Read `~/.claude/skills/lacrimosa/specialists/{name}.md` — this contains your full cycle instructions.

## Step 4: Execute Your Cycle

Follow the instructions in your specialist skill file exactly. You are running ONE cycle.
At the end, your heartbeat is auto-updated by `sm.transaction("{name}")` commit.

There is no Step 5. The process exits after this cycle. The shell loop will respawn
a fresh `claude -p` invocation after the cadence interval.
